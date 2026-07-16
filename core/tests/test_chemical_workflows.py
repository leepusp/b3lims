import html
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Tag
from core.models.chemicals.chemical import Chemical, ChemicalFile
from core.services.metadata_vocabularies import get_or_create_active_keyword_value
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

    def test_list_options_show_edit_and_print_for_owner(self):
        response = self.client.get(request_path("chemicals_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Options")
        self.assertContains(response, "View Details")
        self.assertContains(response, "Edit Reagent")
        self.assertContains(response, "Print QR Label")
        self.assertContains(
            response,
            reverse("chemical_edit", args=[self.chemical.id]),
        )
        self.assertContains(
            response,
            reverse("print_chemical_label", args=[self.chemical.id]),
        )

    def test_list_options_hide_edit_from_read_only_user(self):
        viewer = get_user_model().objects.create_user(
            username="chemical-viewer",
            password="test-password",
        )
        self.chemical.is_public = True
        self.chemical.save(update_fields=["is_public"])

        self.client.force_login(viewer)
        response = self.client.get(request_path("chemicals_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Details")
        self.assertContains(response, "Print QR Label")
        self.assertNotContains(response, "Edit Reagent")

    def test_create_reagent_assigns_tags_and_keywords(self):
        tag = Tag.objects.create(name="Flammable")

        response = self.client.post(
            request_path("chemical_add"),
            {
                "name": "Methanol",
                "quantity_value": "250",
                "quantity_unit": "mL",
                "tags": [str(tag.pk)],
                "keyword_pairs": [
                    "Hazard Class:::Flammable Liquid",
                    "Grade:::HPLC",
                ],
            },
        )

        self.assertEqual(response.status_code, 302)

        chemical = Chemical.objects.get(name="Methanol")

        self.assertTrue(
            chemical.tags.filter(pk=tag.pk).exists()
        )
        self.assertTrue(
            chemical.keywords.filter(
                keyword__name="Hazard Class",
                value="Flammable Liquid",
            ).exists()
        )
        self.assertTrue(
            chemical.keywords.filter(
                keyword__name="Grade",
                value="HPLC",
            ).exists()
        )

    def test_edit_reagent_replaces_active_metadata(self):
        old_tag = Tag.objects.create(name="Old Classification")
        new_tag = Tag.objects.create(name="New Classification")

        old_value, _ = get_or_create_active_keyword_value(
            "Grade",
            "Technical",
        )
        new_value, _ = get_or_create_active_keyword_value(
            "Grade",
            "Analytical",
        )

        self.chemical.tags.add(old_tag)
        self.chemical.keywords.add(old_value)

        response = self.client.post(
            request_path("chemical_edit", [self.chemical.id]),
            {
                "name": self.chemical.name,
                "quantity_value": "500",
                "quantity_unit": "mL",
                "minimum_quantity": "",
                "storage_location": self.chemical.storage_location,
                "storage_temperature": "",
                "status": "available",
                "tags": [str(new_tag.pk)],
                "keyword_pairs": [
                    "Grade:::Analytical",
                ],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.chemical.refresh_from_db()

        self.assertFalse(
            self.chemical.tags.filter(pk=old_tag.pk).exists()
        )
        self.assertTrue(
            self.chemical.tags.filter(pk=new_tag.pk).exists()
        )
        self.assertFalse(
            self.chemical.keywords.filter(
                pk=old_value.pk,
            ).exists()
        )
        self.assertTrue(
            self.chemical.keywords.filter(
                pk=new_value.pk,
            ).exists()
        )

    def test_edit_preserves_archived_metadata_relationships(self):
        archived_tag = Tag.objects.create(
            name="Archived Classification",
            is_active=False,
        )
        archived_value, _ = get_or_create_active_keyword_value(
            "Historical Grade",
            "Legacy",
        )
        archived_value.is_active = False
        archived_value.save(update_fields=["is_active"])

        self.chemical.tags.add(archived_tag)
        self.chemical.keywords.add(archived_value)

        response = self.client.post(
            request_path("chemical_edit", [self.chemical.id]),
            {
                "name": self.chemical.name,
                "quantity_value": "500",
                "quantity_unit": "mL",
                "minimum_quantity": "",
                "storage_location": self.chemical.storage_location,
                "storage_temperature": "",
                "status": "available",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.chemical.tags.filter(
                pk=archived_tag.pk,
            ).exists()
        )
        self.assertTrue(
            self.chemical.keywords.filter(
                pk=archived_value.pk,
            ).exists()
        )

    def test_detail_and_qr_show_active_metadata(self):
        tag = Tag.objects.create(name="Controlled Substance")
        value, _ = get_or_create_active_keyword_value(
            "Storage Class",
            "Locked Cabinet",
        )

        self.chemical.tags.add(tag)
        self.chemical.keywords.add(value)

        detail = self.client.get(
            request_path("chemical_detail", [self.chemical.id])
        )
        qr_page = self.client.get(
            request_path("chemical_qr_scan", [self.chemical.uuid])
        )

        self.assertContains(detail, "Controlled Substance")
        self.assertContains(detail, "Storage Class")
        self.assertContains(detail, "Locked Cabinet")

        self.assertContains(qr_page, "Controlled Substance")
        self.assertContains(qr_page, "Storage Class")
        self.assertContains(qr_page, "Locked Cabinet")
