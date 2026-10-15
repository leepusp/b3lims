import os
import tempfile
import unittest
from pathlib import Path

from deploy.operations.coordinated_release_transaction_v810 import (
    CoordinatedReleaseTransaction,
    CutoverRolledBack,
    RollbackIncomplete,
)


ACTIVE = "a" * 40
TARGET = "b" * 40


class CoordinatedReleaseTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="b3lims-cutover-test-"
        )

        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

        for kind in ("releases", "static-releases"):
            for commit in (ACTIVE, TARGET):
                (self.root / kind / commit).mkdir(
                    parents=True,
                    exist_ok=True,
                )

        (self.root / "current").symlink_to(
            f"releases/{ACTIVE}"
        )

        (self.root / "static-current").symlink_to(
            f"static-releases/{ACTIVE}"
        )

        self.events = []
        self.restart_count = 0
        self.fail_first_restart = False
        self.fail_target_health = False
        self.fail_all_restarts = False

    def links_are(self, commit):
        self.assertEqual(
            os.readlink(self.root / "current"),
            f"releases/{commit}",
        )

        self.assertEqual(
            os.readlink(self.root / "static-current"),
            f"static-releases/{commit}",
        )

    def quiesce(self):
        self.events.append("quiesce")

    def restart(self):
        self.restart_count += 1
        self.events.append("restart")

        if self.fail_all_restarts:
            raise RuntimeError("Service unavailable")

        if (
            self.fail_first_restart
            and self.restart_count == 1
        ):
            raise RuntimeError("First restart failed")

    def verify(self, commit):
        self.events.append(f"verify:{commit}")
        self.links_are(commit)

        if commit == TARGET and self.fail_target_health:
            raise RuntimeError("Target health check failed")

    def transaction(self):
        return CoordinatedReleaseTransaction(
            self.root,
            ACTIVE,
            TARGET,
            self.quiesce,
            self.restart,
            self.verify,
        )

    def test_success_switches_both_links(self):
        result = self.transaction().execute()

        self.assertEqual(result, TARGET)
        self.links_are(TARGET)

        self.assertEqual(
            self.events,
            [
                "quiesce",
                "restart",
                f"verify:{TARGET}",
            ],
        )

    def test_restart_failure_restores_both_links(self):
        self.fail_first_restart = True

        with self.assertRaises(CutoverRolledBack):
            self.transaction().execute()

        self.links_are(ACTIVE)
        self.assertEqual(self.restart_count, 2)
        self.assertIn(f"verify:{ACTIVE}", self.events)

    def test_health_failure_restores_both_links(self):
        self.fail_target_health = True

        with self.assertRaises(CutoverRolledBack):
            self.transaction().execute()

        self.links_are(ACTIVE)
        self.assertIn(f"verify:{ACTIVE}", self.events)

    def test_partial_link_switch_is_rolled_back(self):
        transaction = self.transaction()
        original = transaction._replace_symlink
        injected = False

        def fail_second_link(link, destination):
            nonlocal injected

            if (
                not injected
                and link.name == "static-current"
                and destination.endswith(TARGET)
            ):
                injected = True
                raise RuntimeError("Static link switch failed")

            original(link, destination)

        transaction._replace_symlink = fail_second_link

        with self.assertRaises(CutoverRolledBack):
            transaction.execute()

        self.links_are(ACTIVE)

    def test_mismatched_active_links_fail_before_mutation(self):
        link = self.root / "static-current"
        link.unlink()
        link.symlink_to(f"static-releases/{TARGET}")

        with self.assertRaises(RuntimeError):
            self.transaction().execute()

        self.assertEqual(self.events, [])

    def test_missing_target_fails_before_mutation(self):
        (self.root / "static-releases" / TARGET).rmdir()

        with self.assertRaises(RuntimeError):
            self.transaction().execute()

        self.assertEqual(self.events, [])
        self.links_are(ACTIVE)

    def test_incomplete_rollback_fails_closed(self):
        self.fail_all_restarts = True

        with self.assertRaises(RollbackIncomplete):
            self.transaction().execute()

        self.links_are(ACTIVE)
        self.assertEqual(self.restart_count, 2)

    def test_same_release_is_rejected(self):
        transaction = CoordinatedReleaseTransaction(
            self.root,
            ACTIVE,
            ACTIVE,
            self.quiesce,
            self.restart,
            self.verify,
        )

        with self.assertRaises(RuntimeError):
            transaction.execute()

        self.assertEqual(self.events, [])
        self.links_are(ACTIVE)


if __name__ == "__main__":
    unittest.main()
