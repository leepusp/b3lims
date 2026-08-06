import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from core.models.lab_tools.notebook import (
    notebook_attachment_upload_to,
)
from core.services.jupyter_server import _runner_command
from core.services.lab_tools_storage import (
    UserHomeLabToolsStorage,
    protected_user_path,
    user_lab_tools_root,
)


@override_settings(
    BIOBANK_LAB_TOOLS_RELATIVE_ROOT="biobank/lab_tools",
    BIOBANK_JUPYTER_SERVER_RUNNER=(
        "/usr/local/sbin/biobank-jupyter-server-runner"
    ),
)
class UserHomeLabToolsStorageTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        temporary_root = Path(self.temporary_directory.name)
        self.alice_home = temporary_root / "alice"
        self.bob_home = temporary_root / "bob"
        self.alice_home.mkdir()
        self.bob_home.mkdir()

        def fake_home(username):
            return {
                "alice": self.alice_home,
                "bob": self.bob_home,
            }[username]

        self.home_patch = patch(
            "core.services.lab_tools_storage."
            "user_home_for_username",
            side_effect=fake_home,
        )
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def test_users_have_distinct_private_roots(self):
        self.assertEqual(
            user_lab_tools_root("alice"),
            self.alice_home / "biobank/lab_tools",
        )
        self.assertEqual(
            user_lab_tools_root("bob"),
            self.bob_home / "biobank/lab_tools",
        )

    def test_protected_paths_reject_traversal(self):
        with self.assertRaises(SuspiciousFileOperation):
            protected_user_path(
                "alice",
                "jupyter/../../bob/private.ipynb",
            )

        with self.assertRaises(SuspiciousFileOperation):
            protected_user_path(
                "alice",
                "/home/bob/private.ipynb",
            )

    def test_attachment_name_contains_entry_author(self):
        author = SimpleNamespace(
            get_username=lambda: "alice"
        )
        instance = SimpleNamespace(
            entry_id=31,
            entry=SimpleNamespace(
                author_id=4,
                author=author,
            ),
        )

        name = notebook_attachment_upload_to(
            instance,
            "unsafe report (final).csv",
        )

        self.assertRegex(
            name,
            r"^users/alice/eln/entries/31/attachments/"
            r"[0-9a-f]{32}_unsafe_report_final.csv$",
        )

    def test_save_uses_protected_helper_and_user_home(self):
        storage = UserHomeLabToolsStorage()
        name = (
            "users/alice/eln/entries/31/attachments/"
            "artifact.txt"
        )
        target_directory = (
            self.alice_home
            / "biobank/lab_tools/eln/entries/31/attachments"
        )

        def prepare(_username, _relative):
            target_directory.mkdir(parents=True)
            return target_directory

        with patch(
            "core.services.lab_tools_storage."
            "ensure_user_lab_tools_storage"
        ) as ensure_mock, patch(
            "core.services.lab_tools_storage."
            "prepare_user_storage_directory",
            side_effect=prepare,
        ) as prepare_mock, patch(
            "core.services.lab_tools_storage."
            "claim_user_storage_file",
        ) as claim_mock:
            saved_name = storage.save(
                name,
                ContentFile(b"private artifact\n"),
            )

        self.assertEqual(saved_name, name)
        self.assertEqual(
            Path(storage.path(name)).read_bytes(),
            b"private artifact\n",
        )
        ensure_mock.assert_called_once_with("alice")
        prepare_mock.assert_called_once_with(
            "alice",
            "eln/entries/31/attachments",
        )
        claim_mock.assert_called_once_with(
            "alice",
            "eln/entries/31/attachments/artifact.txt",
        )

    def test_legacy_attachment_remains_readable(self):
        legacy_root = Path(self.temporary_directory.name) / "media"
        legacy_file = (
            legacy_root
            / "notebook/entries/7/attachments/legacy.txt"
        )
        legacy_file.parent.mkdir(parents=True)
        legacy_file.write_text("legacy")
        storage = UserHomeLabToolsStorage()

        with override_settings(MEDIA_ROOT=str(legacy_root)):
            with storage.open(
                "notebook/entries/7/attachments/legacy.txt",
                "rb",
            ) as handle:
                self.assertEqual(handle.read(), b"legacy")

    def test_jupyter_runner_is_invoked_as_root_helper(self):
        self.assertEqual(
            _runner_command("server-status", 4, "alice", "run_1"),
            [
                "sudo",
                "-n",
                "/usr/local/sbin/biobank-jupyter-server-runner",
                "server-status",
                "4",
                "alice",
                "run_1",
            ],
        )
