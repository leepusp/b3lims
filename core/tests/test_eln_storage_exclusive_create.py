"""Regression tests for protected exclusive file creation."""

from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from core.services import lab_tools_storage as storage


class ExclusiveCreateSafetyTests(SimpleTestCase):

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.destination = self.root / "r000001.json"

        self.relative = PurePosixPath(
            "eln/projects/test/entries/"
            "11111111-1111-4111-8111-111111111111/"
            "revisions/r000001.json"
        )

        self.logical = (
            "users/analyst/" + self.relative.as_posix()
        )

        self.backend = storage.UserHomeLabToolsStorage()

    def fake_broker(self):
        from contextlib import ExitStack

        stack = ExitStack()

        stack.enter_context(
            patch.object(
                storage.UserHomeLabToolsStorage,
                "_split_user_name",
                return_value=("analyst", self.relative),
            )
        )

        stack.enter_context(
            patch.object(
                storage,
                "ensure_user_lab_tools_storage",
            )
        )

        stack.enter_context(
            patch.object(
                storage,
                "prepare_user_storage_directory",
                return_value=self.root,
            )
        )

        stack.enter_context(
            patch.object(
                storage,
                "protected_user_path",
                return_value=self.destination,
            )
        )

        return stack

    def test_existing_revision_is_never_deleted(self):
        original = b'{"revision":1,"data":"original"}'

        self.destination.write_bytes(original)

        with self.fake_broker():
            with self.assertRaises(FileExistsError):
                self.backend._save(
                    self.logical,
                    ContentFile(b"replacement"),
                )

        self.assertTrue(self.destination.exists())
        self.assertEqual(
            self.destination.read_bytes(),
            original,
        )

    def test_failed_claim_cleans_only_new_file(self):
        with self.fake_broker():
            with patch.object(
                storage,
                "claim_user_storage_file",
                side_effect=RuntimeError(
                    "Synthetic broker failure"
                ),
            ):
                with self.assertRaises(RuntimeError):
                    self.backend._save(
                        self.logical,
                        ContentFile(b"new data"),
                    )

        self.assertFalse(self.destination.exists())
