import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile
from core.services.sample_data_storage import (
    UserHomeSampleDataStorage,
)


class SampleFileDownloadTests(TestCase):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.user_home = (
            Path(
                self.temporary_directory.name
            )
            / "sampleowner"
        )
        self.user_home.mkdir()

        self.settings_override = override_settings(
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
            return_value=self.user_home,
        )
        self.home_patch.start()
        self.addCleanup(
            self.home_patch.stop
        )

        user_model = get_user_model()

        self.owner = (
            user_model.objects.create_user(
                username="sampleowner",
                password="test-password",
            )
        )

        self.outsider = (
            user_model.objects.create_user(
                username="outsider",
                password="test-password",
            )
        )

        self.sample = Sample.objects.create(
            sample_id="SAMPLE-FILE-DOWNLOAD-1",
            owner=self.owner,
        )

        sample_directory = (
            f"sample_{self.sample.pk}_"
            f"{self.sample.sample_id}"
        )

        self.logical_name = (
            "users/sampleowner/"
            "samples/"
            f"{sample_directory}/"
            "files/report.txt"
        )

        self.physical = (
            self.user_home
            / "biobank"
            / "data"
            / "samples"
            / sample_directory
            / "files"
            / "report.txt"
        )

        self.physical.parent.mkdir(
            parents=True
        )

        self.physical.write_bytes(
            b"protected-download"
        )

        self.sample_file = (
            SampleFile.objects.create(
                sample=self.sample,
                file=self.logical_name,
                description="Download test",
            )
        )

        self.url = reverse(
            "sample_file_download",
            args=[
                self.sample_file.pk
            ],
        )

        script_name = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        ).rstrip("/")

        self.client_path = self.url

        if script_name:
            if self.client_path == script_name:
                self.client_path = "/"

            elif self.client_path.startswith(
                script_name + "/"
            ):
                self.client_path = (
                    self.client_path[
                        len(script_name):
                    ]
                )

    def test_model_uses_strict_user_storage(self):
        field = SampleFile._meta.get_field(
            "file"
        )

        self.assertIsInstance(
            field.storage,
            UserHomeSampleDataStorage,
        )

    def test_owner_can_download(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            b"".join(
                response.streaming_content
            ),
            b"protected-download",
        )

    def test_unauthenticated_user_is_redirected(
        self,
    ):
        response = self.client.get(
            self.client_path
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_unrelated_user_is_forbidden(
        self,
    ):
        self.client.force_login(
            self.outsider
        )

        response = self.client.get(
            self.client_path
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_missing_physical_file_returns_404(
        self,
    ):
        self.physical.unlink()

        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_database_rejects_legacy_file_name(
        self,
    ):
        with self.assertRaises(
            IntegrityError
        ):
            with transaction.atomic():
                (
                    SampleFile.objects
                    .filter(
                        pk=self.sample_file.pk
                    )
                    .update(
                        file=(
                            "_unassigned_samples/"
                            "legacy/report.txt"
                        )
                    )
                )

        self.sample_file.refresh_from_db()

        self.assertEqual(
            self.sample_file.file.name,
            self.logical_name,
        )
