"""B3 LIMS V8.15.2 — institutional presets and import failures."""

from io import BytesIO
from unittest.mock import patch

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from core.models import Biobank, Collection
from core.models.samples.intake import (
    SampleImportBatch,
)
from core.services.sample_intake import import_sample_table


class PreconfiguredImportTemplateTests(TestCase):

    def setUp(self):
        users = get_user_model()

        self.user = users.objects.create_user(
            username="v8152_template_owner",
        )
        self.other = users.objects.create_user(
            username="v8152_template_other",
        )

        self.biobank = Biobank.objects.create(
            name="V8152 Authorized Biobank",
            owner=self.user,
            is_active=True,
        )
        self.collection = Collection.objects.create(
            name="V8152 Authorized Collection",
            owner=self.user,
            is_active=True,
        )
        self.foreign_biobank = Biobank.objects.create(
            name="V8152 Foreign Biobank",
            owner=self.other,
            is_active=True,
        )

        self.client.force_login(self.user)
        self.url = reverse("export_samples_csv")

    def test_preconfigured_xlsx_contains_authorized_defaults(self):
        response = self.client.get(
            self.url,
            {
                "schema": "template",
                "format": "xlsx",
                "preset": "1",
                "biobank_id": str(self.biobank.pk),
                "collection_id": str(self.collection.pk),
            },
        )

        self.assertEqual(response.status_code, 200)

        workbook = load_workbook(
            BytesIO(response.content),
            read_only=True,
        )

        rows = list(workbook["samples"].values)
        headers = list(rows[0])

        self.assertEqual(len(rows), 101)

        first = dict(zip(headers, rows[1]))

        self.assertEqual(
            first["biobank"],
            self.biobank.name,
        )
        self.assertEqual(
            first["collection"],
            self.collection.name,
        )
        self.assertIsNone(first["sample_id"])

    def test_foreign_biobank_is_denied(self):
        response = self.client.get(
            self.url,
            {
                "schema": "template",
                "format": "xlsx",
                "preset": "1",
                "biobank_id": str(self.foreign_biobank.pk),
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_preset_requires_institutional_selection(self):
        response = self.client.get(
            self.url,
            {
                "schema": "template",
                "format": "xlsx",
                "preset": "1",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_preconfigured_template_controls_are_visible(self):
        response = self.client.get(
            reverse("samples_import")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Download preconfigured template",
        )
        self.assertContains(
            response,
            self.biobank.name,
        )
        self.assertNotContains(
            response,
            self.foreign_biobank.name,
        )

    def test_unused_preset_rows_are_ignored(self):
        rows = pd.DataFrame([
            {
                "sample_id": "V8152-EXTERNAL-001",
                "sample_type": "Other",
                "organism_name": "External QA Material",
                "biobank": self.biobank.name,
                "collection": self.collection.name,
            },
            {
                "sample_id": "",
                "sample_type": "",
                "organism_name": "",
                "biobank": self.biobank.name,
                "collection": self.collection.name,
            },
        ])

        batch = SampleImportBatch.objects.create(
            uploaded_by=self.user,
            original_file="sample_imports/v8152_test.xlsx",
        )

        with patch(
            "core.services.sample_intake.read_sample_table",
            return_value=rows,
        ):
            import_sample_table(batch)

        batch.refresh_from_db()

        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(batch.valid_rows, 1)
        self.assertEqual(batch.invalid_rows, 0)
        self.assertEqual(batch.records.count(), 1)

    def test_missing_sample_id_with_other_data_is_not_ignored(self):
        rows = pd.DataFrame([{
            "sample_id": "",
            "sample_type": "Other",
            "organism_name": "Incomplete Sample",
            "biobank": self.biobank.name,
        }])

        batch = SampleImportBatch.objects.create(
            uploaded_by=self.user,
            original_file="sample_imports/v8152_test.xlsx",
        )

        with patch(
            "core.services.sample_intake.read_sample_table",
            return_value=rows,
        ):
            import_sample_table(batch)

        batch.refresh_from_db()

        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(batch.invalid_rows, 1)

    def test_only_unused_rows_fail_cleanly(self):
        rows = pd.DataFrame([{
            "sample_id": "",
            "sample_type": "",
            "organism_name": "",
            "biobank": self.biobank.name,
        }])

        batch = SampleImportBatch.objects.create(
            uploaded_by=self.user,
            original_file="sample_imports/v8152_test.xlsx",
        )

        with patch(
            "core.services.sample_intake.read_sample_table",
            return_value=rows,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "No Sample rows found",
            ):
                import_sample_table(batch)

        self.assertEqual(batch.records.count(), 0)


class FailedImportBatchTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="v8152_import_failure",
        )
        self.client.force_login(self.user)

        self.batch = SampleImportBatch.objects.create(
            uploaded_by=self.user,
            original_file="sample_imports/v8152_failure.csv",
        )

    def upload(self):
        return SimpleUploadedFile(
            "invalid.csv",
            b"invalid",
            content_type="text/csv",
        )

    def test_validation_error_is_persisted(self):
        with (
            patch(
                "core.views.internal.samples.views."
                "SampleImportBatch.objects.create",
                return_value=self.batch,
            ),
            patch(
                "core.views.internal.samples.views."
                "import_sample_table",
                side_effect=ValueError(
                    "Missing required columns: sample_id"
                ),
            ),
        ):
            response = self.client.post(
                reverse("samples_import"),
                {"sample_table": self.upload()},
            )

        self.assertEqual(response.status_code, 302)

        self.batch.refresh_from_db()

        self.assertEqual(self.batch.status, "failed")
        self.assertIn(
            "Missing required columns",
            self.batch.notes,
        )

        detail = self.client.get(
            reverse(
                "samples_import_batch",
                args=[self.batch.pk],
            )
        )

        self.assertContains(
            detail,
            "Import failed.",
        )

    def test_unexpected_exception_has_safe_message(self):
        with (
            patch(
                "core.views.internal.samples.views."
                "SampleImportBatch.objects.create",
                return_value=self.batch,
            ),
            patch(
                "core.views.internal.samples.views."
                "import_sample_table",
                side_effect=RuntimeError(
                    "Sensitive internal diagnostic"
                ),
            ),
            self.assertLogs(
                "core.views.internal.samples.views",
                level="ERROR",
            ),
        ):
            response = self.client.post(
                reverse("samples_import"),
                {"sample_table": self.upload()},
            )

        self.assertEqual(response.status_code, 302)

        self.batch.refresh_from_db()

        self.assertEqual(self.batch.status, "failed")
        self.assertNotIn(
            "Sensitive internal diagnostic",
            self.batch.notes,
        )


class RealUploadRoundTripV8152Tests(TestCase):
    """Real HTTP uploads with isolated test database and media."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="v8152_http_roundtrip",
        )
        self.biobank = Biobank.objects.create(
            name="V8152 HTTP Test Biobank",
            owner=self.user,
            is_active=True,
        )
        self.collection = Collection.objects.create(
            name="V8152 HTTP Test Collection",
            owner=self.user,
            is_active=True,
        )
        self.client.force_login(self.user)

    def _preset_xlsx(self, fill_sample=True):
        response = self.client.get(
            reverse("export_samples_csv"),
            {
                "schema": "template",
                "format": "xlsx",
                "preset": "1",
                "biobank_id": str(self.biobank.pk),
                "collection_id": str(self.collection.pk),
            },
        )

        self.assertEqual(response.status_code, 200)

        workbook = load_workbook(
            BytesIO(response.content)
        )

        sheet = workbook["samples"]

        if fill_sample:
            headers = [
                cell.value
                for cell in sheet[1]
            ]

            values = {
                "sample_id": "000008152",
                "sample_type": "Other",
                "organism_name": "Synthetic HTTP QA",
                "is_public": "false",
            }

            for name, value in values.items():
                column = headers.index(name) + 1

                sheet.cell(
                    row=2,
                    column=column,
                    value=value,
                )

        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()

        return buffer.getvalue()

    def test_real_preconfigured_xlsx_http_upload(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from core.models import Sample

        with TemporaryDirectory(
            prefix="b3lims-v8152-http-"
        ) as directory, override_settings(
            MEDIA_ROOT=directory
        ):
            upload = SimpleUploadedFile(
                "external_samples.xlsx",
                self._preset_xlsx(),
                content_type=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
            )

            response = self.client.post(
                reverse("samples_import"),
                {"sample_table": upload},
            )

            self.assertEqual(response.status_code, 302)

            batch = SampleImportBatch.objects.get(
                uploaded_by=self.user
            )

            self.assertEqual(batch.status, "validated")
            self.assertEqual(batch.total_rows, 1)
            self.assertEqual(batch.valid_rows, 1)
            self.assertEqual(batch.invalid_rows, 0)
            self.assertEqual(batch.records.count(), 1)

            record = batch.records.get()

            self.assertEqual(
                record.imported_sample_id,
                "000008152",
            )
            self.assertEqual(
                record.matched_biobank_id,
                self.biobank.pk,
            )
            self.assertEqual(
                record.matched_collection_id,
                self.collection.pk,
            )
            self.assertEqual(record.row_number, 2)

            self.assertFalse(
                Sample.objects.filter(
                    sample_id="000008152"
                ).exists()
            )

    def test_real_semicolon_csv_http_upload(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from core.models import Sample

        body = (
            "sample_id;sample_type;organism_name\n"
            "000008153;Other;Synthetic CSV QA\n"
        ).encode("utf-8")

        with TemporaryDirectory(
            prefix="b3lims-v8152-csv-"
        ) as directory, override_settings(
            MEDIA_ROOT=directory
        ):
            response = self.client.post(
                reverse("samples_import"),
                {
                    "sample_table": SimpleUploadedFile(
                        "external_samples.csv",
                        body,
                        content_type="text/csv",
                    ),
                },
            )

            self.assertEqual(response.status_code, 302)

            batch = SampleImportBatch.objects.get(
                uploaded_by=self.user
            )

            self.assertEqual(batch.status, "validated")
            self.assertEqual(batch.total_rows, 1)
            self.assertEqual(batch.valid_rows, 1)
            self.assertEqual(batch.invalid_rows, 0)

            self.assertEqual(
                batch.records.get().imported_sample_id,
                "000008153",
            )

            self.assertFalse(
                Sample.objects.filter(
                    sample_id="000008153"
                ).exists()
            )

    def test_real_invalid_upload_persists_failure(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings

        with TemporaryDirectory(
            prefix="b3lims-v8152-invalid-"
        ) as directory, override_settings(
            MEDIA_ROOT=directory
        ):
            response = self.client.post(
                reverse("samples_import"),
                {
                    "sample_table": SimpleUploadedFile(
                        "invalid.csv",
                        b"wrong_header;other\nabc;123\n",
                        content_type="text/csv",
                    ),
                },
            )

            self.assertEqual(response.status_code, 302)

            batch = SampleImportBatch.objects.get(
                uploaded_by=self.user
            )

            self.assertEqual(batch.status, "failed")
            self.assertIn(
                "Missing required columns",
                batch.notes,
            )
            self.assertEqual(batch.records.count(), 0)

    def test_unused_preconfigured_xlsx_fails_cleanly(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings

        with TemporaryDirectory(
            prefix="b3lims-v8152-empty-"
        ) as directory, override_settings(
            MEDIA_ROOT=directory
        ):
            response = self.client.post(
                reverse("samples_import"),
                {
                    "sample_table": SimpleUploadedFile(
                        "empty_preset.xlsx",
                        self._preset_xlsx(
                            fill_sample=False
                        ),
                        content_type=(
                            "application/vnd.openxmlformats-"
                            "officedocument.spreadsheetml.sheet"
                        ),
                    ),
                },
            )

            self.assertEqual(response.status_code, 302)

            batch = SampleImportBatch.objects.get(
                uploaded_by=self.user
            )

            self.assertEqual(batch.status, "failed")
            self.assertEqual(batch.records.count(), 0)
            self.assertIn(
                "No Sample rows found",
                batch.notes,
            )
