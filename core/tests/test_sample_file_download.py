import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
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

        self.media_root = (
            Path(
                self.temporary_directory.name
            )
            / "media"
        )
        self.media_root.mkdir()

        self.settings_override = override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_URL="/biobank/data/",
        )
        self.settings_override.enable()
        self.addCleanup(
            self.settings_override.disable
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

        physical = (
            self.media_root
            / "_unassigned_samples"
            / "download-test"
            / "report.txt"
        )
        physical.parent.mkdir(
            parents=True
        )
        physical.write_bytes(
            b"protected-download"
        )

        self.sample_file = (
            SampleFile.objects.create(
                sample=self.sample,
                file=(
                    "_unassigned_samples/"
                    "download-test/report.txt"
                ),
                description="Download test",
            )
        )

        self.url = reverse(
            "sample_file_download",
            args=[
                self.sample_file.pk
            ],
        )

        # reverse() correctly includes FORCE_SCRIPT_NAME for
        # browser-facing URLs. Django's test Client expects
        # PATH_INFO, where the WSGI server has already removed
        # SCRIPT_NAME.
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

    def test_model_uses_hybrid_storage(self):
        field = (
            SampleFile._meta.get_field(
                "file"
            )
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
        Path(
            self.sample_file.file.path
        ).unlink()

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
