from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse

from core.models import SampleImportBatch
from core.models.samples.intake import SampleIntakeRecord
from core.services.sample_intake import update_intake_record


class ImportRowEditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("row-editor", password="x")
        self.client.force_login(self.user)
        self.batch = SampleImportBatch.objects.create(
            uploaded_by=self.user, original_filename="t.csv", total_rows=2, invalid_rows=2,
            original_file=ContentFile(b"x", name="t.csv"),
        )
        self.first = SampleIntakeRecord.objects.create(
            batch=self.batch, row_number=2, imported_sample_id="BAC-1", sample_type="Bacterium",
            organism_name="", normalized_data={"sample_id": "BAC-1", "sample_type": "Bacterium"},
            validation_errors=["Organism name is required."], status="waiting_review",
        )
        self.second = SampleIntakeRecord.objects.create(
            batch=self.batch, row_number=3, imported_sample_id="BAC-2", sample_type="Bacterium",
            normalized_data={"sample_id": "BAC-2", "sample_type": "Bacterium", "organism_name": "Escherichia coli"},
            validation_errors=[], status="ready_to_fill",
        )

    def test_edit_fixes_row_and_counters(self):
        url = reverse("samples_import_record_edit", args=[self.first.pk])
        self.client.post(url, {"sample_id": "BAC-1", "sample_type": "Bacterium", "organism_name": "Escherichia coli"})
        self.first.refresh_from_db()
        self.batch.refresh_from_db()

        self.assertEqual(self.first.organism_name, "Escherichia coli")
        self.assertEqual(self.first.validation_errors, [])
        self.assertEqual(self.first.status, "ready_to_fill")
        self.assertEqual(self.batch.invalid_rows, 0)
        self.assertEqual(self.batch.valid_rows, 2)

    def test_duplicate_id_inside_batch_is_reported(self):
        update_intake_record(self.first, {"sample_id": "BAC-2", "sample_type": "Bacterium", "organism_name": "E. coli"})
        self.first.refresh_from_db()

        self.assertTrue(self.first.validation_errors)
        self.assertEqual(self.first.status, "waiting_review")

    def test_only_uploader_can_edit_and_page_shows_edit_button(self):
        page = self.client.get(reverse("samples_import_batch", args=[self.batch.pk]))
        self.assertContains(page, "data-import-edit")

        other = get_user_model().objects.create_user("intruder", password="x")
        self.client.force_login(other)
        response = self.client.post(reverse("samples_import_record_edit", args=[self.first.pk]), {"organism_name": "x"})
        self.assertEqual(response.status_code, 403)
