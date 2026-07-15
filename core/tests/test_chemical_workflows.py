import html
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.chemicals.chemical import Chemical, ChemicalFile
from core.permissions.chemicals import visible_chemicals_for_user


def request_path(name, args=None):
    """Test client path without the production Apache script prefix."""
    return reverse(name, args=args).removeprefix("/biobank")


class ChemicalWorkflowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.media_directory.name,
            FORCE_SCRIPT_NAME=None,
        )
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        cls.media_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chemical-owner",
            password="test-password",
        )
        self.chemical = Chemical.objects.create(
            name="Ethanol 70%",
            quantity="500 mL",
            quantity_value="500.000",
            quantity_unit="mL",
            storage_location="Room 2 > Cabinet A > Shelf 3",
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_deactivation_preserves_record_and_hides_it(self):
        response = self.client.post(
            request_path("chemical_delete", [self.chemical.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("chemicals_list"))
        self.chemical.refresh_from_db()
        self.assertFalse(self.chemical.is_active)
        self.assertFalse(visible_chemicals_for_user(self.user).filter(pk=self.chemical.pk).exists())
        self.assertEqual(
            self.client.get(request_path("chemical_detail", [self.chemical.id])).status_code,
            404,
        )

    def test_document_metadata_download_soft_remove_and_qr(self):
        upload = SimpleUploadedFile(
            "ethanol-sds.pdf",
            b"%PDF-1.4\nreagent safety data\n%%EOF",
            content_type="application/pdf",
        )
        response = self.client.post(
            request_path("chemical_file_add", [self.chemical.id]),
            {
                "file": upload,
                "title": "Ethanol Safety Data Sheet",
                "document_type": "sds",
                "version": "3.2",
                "document_date": "2026-07-15",
                "description": "Supplier safety documentation",
                "is_primary": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("chemical_detail", args=[self.chemical.id]))
        document = ChemicalFile.objects.get(chemical=self.chemical)
        self.assertEqual(document.original_filename, "ethanol-sds.pdf")
        self.assertEqual(document.document_type, "sds")
        self.assertTrue(document.is_primary)
        self.assertTrue(document.file.name.startswith(f"chemicals/{self.chemical.uuid}/documents/"))
        self.assertNotIn("ethanol-sds", document.file.name)
        self.assertTrue(Path(document.file.path).exists())

        download = self.client.get(
            request_path("chemical_file_download", [self.chemical.id, document.id]),
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")

        qr_page = self.client.get(request_path("chemical_qr_scan", [self.chemical.uuid]))
        self.assertContains(qr_page, "Open Primary Safety Data Sheet")
        self.assertContains(qr_page, html.escape(self.chemical.storage_location))

        remove = self.client.post(
            request_path("chemical_file_remove", [self.chemical.id, document.id]),
        )
        self.assertEqual(remove.status_code, 302)
        document.refresh_from_db()
        self.assertFalse(document.is_active)
        self.assertFalse(document.is_primary)
        self.assertTrue(Path(document.file.path).exists())

    def test_qr_requires_authentication_and_print_label_contains_qr(self):
        self.client.logout()
        scan_url = request_path("chemical_qr_scan", [self.chemical.uuid])
        response = self.client.get(scan_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

        self.client.force_login(self.user)
        label = self.client.get(request_path("print_chemical_label", [self.chemical.id]))
        self.assertContains(label, "data:image/png;base64,")
        self.assertContains(label, self.chemical.name)

    def test_edit_page_keeps_existing_structured_location(self):
        response = self.client.get(request_path("chemical_edit", [self.chemical.id]))
        self.assertContains(response, html.escape(self.chemical.storage_location))
        self.assertContains(response, "data-storage-builder")
        self.assertContains(response, "internal/chemicals/chemical.js")
