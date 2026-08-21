from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile


class SampleDetailViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="sampleowner",
            password="test-password",
        )

        self.outsider = user_model.objects.create_user(
            username="sampleoutsider",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="DETAIL-2026-001",
            sample_type="Plasmid",
            organism_name="Example construct",
            biosafety_level="NB-1",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
            scientific_notes=(
                "Validated scientific notes."
            ),
        )

        logical_name = (
            "users/sampleowner/"
            "samples/"
            f"sample_{self.sample.pk}_"
            "DETAIL-2026-001/"
            "files/report.pdf"
        )

        # This fixture represents an already persisted SampleFile.
        # Use bulk_create so the model's physical-storage save hook
        # is not invoked for the synthetic Django-only test user.
        SampleFile.objects.bulk_create(
            [
                SampleFile(
                    sample=self.sample,
                    file=logical_name,
                    description="Validation report",
                    mime_type="application/pdf",
                    file_size=2048,
                    category="pdf",
                )
            ]
        )

        self.sample_file = SampleFile.objects.get(
            sample=self.sample
        )

        self.url = reverse(
            "sample_detail",
            args=[
                self.sample.pk
            ],
        )

        self.client_path = self._client_path(
            self.url
        )

    @staticmethod
    def _client_path(url):
        script_name = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        ).rstrip("/")

        if not script_name:
            return url

        if url == script_name:
            return "/"

        if url.startswith(
            script_name + "/"
        ):
            return url[
                len(script_name):
            ]

        return url

    def test_owner_can_view_sample_detail(
        self,
    ):
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

        self.assertContains(
            response,
            "Ownership & Governance",
        )

        self.assertContains(
            response,
            "Physical Storage",
        )

        self.assertContains(
            response,
            "Scientific Notes",
        )

        self.assertContains(
            response,
            "Available / Approved",
        )

        self.assertContains(
            response,
            "No collections assigned.",
        )

        self.assertContains(
            response,
            "No physical storage location assigned.",
        )

    def test_file_metadata_does_not_expose_internal_path(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path
        )

        self.assertContains(
            response,
            "report.pdf",
        )

        self.assertContains(
            response,
            "PDF Document",
        )

        self.assertContains(
            response,
            "application/pdf",
        )

        self.assertContains(
            response,
            "Validation report",
        )

        self.assertNotContains(
            response,
            "users/sampleowner/",
        )

        self.assertNotContains(
            response,
            "Legacy location",
        )

    def test_file_link_uses_protected_download_route(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path
        )

        download_url = reverse(
            "sample_file_download",
            args=[
                self.sample_file.pk
            ],
        )

        self.assertContains(
            response,
            download_url,
        )

    def test_private_sample_forbids_unrelated_user(
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

    def test_sample_status_labels_are_english(
        self,
    ):
        self.assertEqual(
            dict(
                Sample.STATUS_CHOICES
            ),
            {
                "pending": "Pending Receipt",
                "qc": "Quality Control",
                "available": "Available / Approved",
                "rejected": "Rejected / Nonviable",
                "depleted": "Depleted",
            },
        )

    def test_samplefile_filename_returns_basename(
        self,
    ):
        self.assertEqual(
            self.sample_file.filename,
            "report.pdf",
        )
