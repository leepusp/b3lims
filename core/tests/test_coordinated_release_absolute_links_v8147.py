import os
import tempfile
import unittest
from pathlib import Path

from deploy.operations.coordinated_release_transaction_v810 import (
    CoordinatedReleaseTransaction,
    CutoverRolledBack,
)


OLD = "a" * 40
NEW = "b" * 40


class CoordinatedReleaseAbsoluteLinksTests(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(
            prefix="b3lims-c4h-"
        )
        self.addCleanup(temporary.cleanup)

        self.root = Path(temporary.name)

        for kind in ("releases", "static-releases"):
            for commit in (OLD, NEW):
                (
                    self.root / kind / commit
                ).mkdir(parents=True)

    def install_links(self, absolute):
        for link_name, kind in (
            ("current", "releases"),
            ("static-current", "static-releases"),
        ):
            destination = (
                str(self.root / kind / OLD)
                if absolute
                else f"{kind}/{OLD}"
            )
            (self.root / link_name).symlink_to(destination)

    def assert_links(self, commit, absolute):
        for link_name, kind in (
            ("current", "releases"),
            ("static-current", "static-releases"),
        ):
            expected = (
                str(self.root / kind / commit)
                if absolute
                else f"{kind}/{commit}"
            )
            self.assertEqual(
                os.readlink(self.root / link_name),
                expected,
            )

    def transaction(self, verify):
        return CoordinatedReleaseTransaction(
            app_root=self.root,
            active_commit=OLD,
            target_commit=NEW,
            quiesce=lambda: None,
            restart=lambda: None,
            verify=verify,
        )

    def test_absolute_links_switch_successfully(self):
        self.install_links(absolute=True)

        def verify(commit):
            self.assert_links(
                commit,
                absolute=True,
            )

        result = self.transaction(verify).execute()

        self.assertEqual(result, NEW)
        self.assert_links(NEW, absolute=True)

    def test_absolute_links_preserved_on_rollback(self):
        self.install_links(absolute=True)

        def verify(commit):
            self.assert_links(
                commit,
                absolute=True,
            )

            if commit == NEW:
                raise RuntimeError(
                    "Simulated target health failure"
                )

        with self.assertRaises(CutoverRolledBack):
            self.transaction(verify).execute()

        self.assert_links(OLD, absolute=True)

    def test_relative_links_remain_supported(self):
        self.install_links(absolute=False)

        def verify(commit):
            self.assert_links(
                commit,
                absolute=False,
            )

        result = self.transaction(verify).execute()

        self.assertEqual(result, NEW)
        self.assert_links(NEW, absolute=False)

    def test_mismatched_link_format_is_rejected(self):
        self.install_links(absolute=True)

        link = self.root / "static-current"
        link.unlink()
        link.symlink_to(f"static-releases/{OLD}")

        with self.assertRaises(RuntimeError):
            self.transaction(
                lambda commit: None
            ).execute()

        self.assertEqual(
            os.readlink(self.root / "current"),
            str(self.root / "releases" / OLD),
        )
        self.assertEqual(
            os.readlink(link),
            f"static-releases/{OLD}",
        )

    def test_unexpected_absolute_target_is_rejected(self):
        self.install_links(absolute=True)

        link = self.root / "current"
        link.unlink()
        link.symlink_to(
            str(self.root / "releases" / NEW)
        )

        with self.assertRaises(RuntimeError):
            self.transaction(
                lambda commit: None
            ).execute()

        self.assertEqual(
            os.readlink(link),
            str(self.root / "releases" / NEW),
        )
