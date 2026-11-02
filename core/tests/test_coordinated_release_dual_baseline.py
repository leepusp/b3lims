"""Tests for coordinated releases with distinct active IDs.

Filesystem-only tests. No service, database or network access.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from deploy.operations.coordinated_release_transaction_v810 import (
    CoordinatedReleaseTransaction,
    CutoverRolledBack,
)


class DualBaselineTransactionTests(SimpleTestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.root = Path(temp.name)
        self.app_old = "a" * 40
        self.static_old = "b" * 40
        self.target = "c" * 40

        for kind, commit in (
            ("releases", self.app_old),
            ("static-releases", self.static_old),
            ("releases", self.target),
            ("static-releases", self.target),
        ):
            (self.root / kind / commit).mkdir(
                parents=True,
            )

        self.app_link = self.root / "current"
        self.static_link = self.root / "static-current"

        self.app_link.symlink_to(
            f"releases/{self.app_old}"
        )

        self.static_link.symlink_to(
            f"static-releases/{self.static_old}"
        )

        self.events = []

    def transaction(
        self,
        *,
        static_baseline=None,
        verify=None,
    ):
        if verify is None:
            verify = lambda commit: self.events.append(
                ("verify", commit)
            )

        return CoordinatedReleaseTransaction(
            app_root=self.root,
            active_commit=self.app_old,
            target_commit=self.target,
            active_static_commit=static_baseline,
            quiesce=lambda: self.events.append("quiesce"),
            restart=lambda: self.events.append("restart"),
            verify=verify,
        )

    def test_distinct_baselines_can_be_activated(self):
        transaction = self.transaction(
            static_baseline=self.static_old,
        )

        result = transaction.execute()

        self.assertEqual(result, self.target)
        self.assertEqual(
            self.app_link.resolve(),
            self.root / "releases" / self.target,
        )
        self.assertEqual(
            self.static_link.resolve(),
            self.root / "static-releases" / self.target,
        )
        self.assertEqual(self.events[0], "quiesce")

    def test_failed_verification_restores_both_baselines(self):
        def verify(commit):
            if commit == self.target:
                raise RuntimeError("Synthetic health failure")

        transaction = self.transaction(
            static_baseline=self.static_old,
            verify=verify,
        )

        with self.assertRaises(CutoverRolledBack):
            transaction.execute()

        self.assertEqual(
            self.app_link.resolve(),
            self.root / "releases" / self.app_old,
        )

        self.assertEqual(
            self.static_link.resolve(),
            self.root / "static-releases" / self.static_old,
        )

        self.assertEqual(
            self.events.count("restart"),
            2,
        )

    def test_missing_target_static_blocks_cutover(self):
        (self.root / "static-releases" / self.target).rmdir()

        transaction = self.transaction(
            static_baseline=self.static_old,
        )

        with self.assertRaises(RuntimeError):
            transaction.execute()

        self.assertEqual(self.events, [])

    def test_invalid_active_static_id_is_rejected(self):
        transaction = self.transaction(
            static_baseline="invalid",
        )

        with self.assertRaises(RuntimeError):
            transaction.execute()

        self.assertEqual(self.events, [])

    def test_legacy_default_rejects_mismatched_baseline(self):
        transaction = self.transaction()

        with self.assertRaises(RuntimeError):
            transaction.execute()

        self.assertEqual(self.events, [])

    def test_legacy_default_still_supports_equal_baselines(self):
        self.static_link.unlink()

        (self.root / "static-releases" / self.app_old).mkdir()

        self.static_link.symlink_to(
            f"static-releases/{self.app_old}"
        )

        transaction = self.transaction()

        self.assertEqual(
            transaction.execute(),
            self.target,
        )
