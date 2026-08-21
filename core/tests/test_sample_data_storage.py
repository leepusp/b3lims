import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from core.models.samples.sample_files import (
    sample_file_upload_to,
)
from core.services.sample_data_storage import (
    UserHomeSampleDataStorage,
)


class UserHomeSampleDataStorageTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(
            self.temporary_directory.cleanup
        )

        root = Path(
            self.temporary_directory.name
        )

        self.media_root = root / "media"
        self.media_root.mkdir()

        self.home = root / "alice"
        self.home.mkdir()

        self.settings_override = override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_URL="/biobank/data/",
            BIOBANK_SAMPLE_DATA_RELATIVE_ROOT=(
                "biobank/data"
            ),
        )
        self.settings_override.enable()
        self.addCleanup(
            self.settings_override.disable
        )

        self.home_patch = patch(
            "core.services.sample_data_storage."
            "user_home_for_username",
            return_value=self.home,
        )
        self.home_patch.start()
        self.addCleanup(
            self.home_patch.stop
        )

        self.storage = (
            UserHomeSampleDataStorage()
        )

    def _sample(self):
        return SimpleNamespace(
            pk=18,
            sample_id="PLA-2026-5515",
            owner=SimpleNamespace(
                username="alice",
            ),
        )

    def test_upload_name_uses_owner_and_sample_identity(
        self,
    ):
        instance = SimpleNamespace(
            sample=self._sample()
        )

        name = sample_file_upload_to(
            instance,
            "pET-28a.pdf",
        )

        self.assertEqual(
            name,
            (
                "users/alice/samples/"
                "sample_18_PLA-2026-5515/"
                "files/pET-28a.pdf"
            ),
        )

    def test_sample_identifier_has_dedicated_directory(
        self,
    ):
        instance = SimpleNamespace(
            sample=self._sample()
        )

        name = sample_file_upload_to(
            instance,
            "report.txt",
        )

        parts = name.split("/")

        self.assertEqual(
            parts,
            [
                "users",
                "alice",
                "samples",
                "sample_18_PLA-2026-5515",
                "files",
                "report.txt",
            ],
        )

        self.assertEqual(
            parts[3],
            "sample_18_PLA-2026-5515",
        )

        self.assertIn(
            "PLA-2026-5515",
            parts[3],
        )

    def test_filename_is_sanitized(self):
        instance = SimpleNamespace(
            sample=self._sample()
        )

        name = sample_file_upload_to(
            instance,
            "../../unsafe file?.txt",
        )

        self.assertEqual(
            name,
            (
                "users/alice/samples/"
                "sample_18_PLA-2026-5515/"
                "files/unsafe_file_.txt"
            ),
        )

    def test_legacy_media_root_file_still_opens(
        self,
    ):
        legacy = (
            self.media_root
            / "_unassigned_samples"
            / "legacy"
            / "report.txt"
        )

        legacy.parent.mkdir(
            parents=True
        )

        legacy.write_bytes(
            b"legacy-data"
        )

        name = (
            "_unassigned_samples/"
            "legacy/report.txt"
        )

        self.assertEqual(
            Path(
                self.storage.path(name)
            ),
            legacy,
        )

        with self.storage.open(
            name,
            "rb",
        ) as handle:
            self.assertEqual(
                handle.read(),
                b"legacy-data",
            )

        self.assertEqual(
            self.storage.url(name),
            (
                "/biobank/data/"
                "_unassigned_samples/"
                "legacy/report.txt"
            ),
        )

    def test_legacy_path_traversal_is_rejected(
        self,
    ):
        with self.assertRaises(
            SuspiciousFileOperation
        ):
            self.storage.path(
                "../outside.txt"
            )

    def test_per_user_path_resolves_under_data_root(
        self,
    ):
        name = (
            "users/alice/samples/"
            "sample_18_PLA-2026-5515/"
            "files/report.txt"
        )

        expected = (
            self.home
            / "biobank"
            / "data"
            / "samples"
            / "sample_18_PLA-2026-5515"
            / "files"
            / "report.txt"
        )

        self.assertEqual(
            Path(
                self.storage.path(name)
            ),
            expected,
        )

    def test_per_user_url_is_not_public(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            self.storage.url(
                (
                    "users/alice/samples/"
                    "sample_18_PLA-2026-5515/"
                    "files/report.txt"
                )
            )

    def test_save_uses_sample_data_runner_contract(
        self,
    ):
        files_directory = (
            self.home
            / "biobank"
            / "data"
            / "samples"
            / "sample_18_PLA-2026-5515"
            / "files"
        )

        def prepare(
            username,
            relative,
        ):
            self.assertEqual(
                username,
                "alice",
            )
            self.assertEqual(
                relative,
                (
                    "samples/"
                    "sample_18_PLA-2026-5515/"
                    "files"
                ),
            )

            files_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            return files_directory

        with (
            patch(
                "core.services."
                "sample_data_storage."
                "prepare_sample_data_directory",
                side_effect=prepare,
            ),
            patch(
                "core.services."
                "sample_data_storage."
                "claim_sample_data_file",
            ) as claim,
        ):
            saved = self.storage.save(
                (
                    "users/alice/samples/"
                    "sample_18_PLA-2026-5515/"
                    "files/report.txt"
                ),
                ContentFile(
                    b"protected-sample-data"
                ),
            )

        self.assertEqual(
            saved,
            (
                "users/alice/samples/"
                "sample_18_PLA-2026-5515/"
                "files/report.txt"
            ),
        )

        destination = (
            files_directory
            / "report.txt"
        )

        self.assertEqual(
            destination.read_bytes(),
            b"protected-sample-data",
        )

        claim.assert_called_once_with(
            "alice",
            (
                "samples/"
                "sample_18_PLA-2026-5515/"
                "files/report.txt"
            ),
        )
