"""V8.15.1 selected Sample export security regressions."""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from core.models import Sample


class SelectedSampleExportV8151Tests(TestCase):

    def setUp(self):
        user_model = get_user_model()

        self.user = user_model.objects.create_user(
            username="export_selected_v8151",
        )
        self.other = user_model.objects.create_user(
            username="export_other_v8151",
        )

        self.own_sample = Sample.objects.create(
            sample_id="EXPORT-QA-OWN-8151",
            sample_type="Other",
            organism_name="Own QA Sample",
            owner=self.user,
        )

        self.foreign_sample = Sample.objects.create(
            sample_id="EXPORT-QA-FOREIGN-8151",
            sample_type="Other",
            organism_name="Foreign QA Sample",
            owner=self.other,
            is_public=False,
        )

        self.url = reverse("export_samples_csv")
        self.client.force_login(self.user)

    def test_export_one_selected_sample_as_xlsx(self):
        response = self.client.post(
            self.url,
            {
                "format": "xlsx",
                "schema": "standard",
                "sample_ids": [
                    str(self.own_sample.pk),
                ],
            },
        )

        self.assertEqual(response.status_code, 200)

        workbook = load_workbook(
            BytesIO(response.content),
            read_only=True,
        )

        worksheet = workbook["samples"]
        rows = list(worksheet.values)

        headers = list(rows[0])
        sample_id_index = headers.index("sample_id")

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[1][sample_id_index],
            "EXPORT-QA-OWN-8151",
        )

    def test_foreign_private_sample_is_not_exported(self):
        response = self.client.post(
            self.url,
            {
                "format": "csv",
                "sample_ids": [
                    str(self.foreign_sample.pk),
                ],
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_mixed_selection_is_rejected_entirely(self):
        response = self.client.post(
            self.url,
            {
                "format": "csv",
                "sample_ids": [
                    str(self.own_sample.pk),
                    str(self.foreign_sample.pk),
                ],
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_empty_selection_is_rejected(self):
        response = self.client.post(
            self.url,
            {"format": "csv"},
        )

        self.assertEqual(response.status_code, 400)

    def test_duplicate_selection_is_rejected(self):
        pk = str(self.own_sample.pk)

        response = self.client.post(
            self.url,
            {
                "sample_ids": [pk, pk],
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_identifier_is_rejected(self):
        response = self.client.post(
            self.url,
            {"sample_ids": ["1 OR 1=1"]},
        )

        self.assertEqual(response.status_code, 400)

    def test_selection_cannot_request_template(self):
        response = self.client.post(
            self.url,
            {
                "schema": "template",
                "sample_ids": [
                    str(self.own_sample.pk),
                ],
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_inventory_renders_selected_export(self):
        response = self.client.get(
            reverse("samples_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="exportSelectedSamplesButton"',
        )
        self.assertContains(
            response,
            'id="exportSelectedSamplesForm"',
        )
