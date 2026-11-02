"""B3 LIMS V8.15.1 — sample table compatibility tests."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from openpyxl import load_workbook

from core.models.samples.intake import SampleImportBatch
from core.services.sample_intake import (
    import_sample_table,
    read_sample_table,
)
from core.services.sample_export import _sample_to_row


class ImportReaderV8151Tests(SimpleTestCase):

    def test_semicolon_csv_preserves_identifier(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "samples.csv"

            path.write_text(
                "sample_id;sample_type;organism_name\n"
                "000123;Phage (Virus);Phage QA\n",
                encoding="utf-8",
            )

            data = read_sample_table(path)

            self.assertEqual(len(data), 1)
            self.assertEqual(
                data.iloc[0]["sample_id"],
                "000123",
            )

            self.assertIn("sample_type", data.columns)

    def test_excel_preserves_text_identifier(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "samples.xlsx"

            pd.DataFrame([{
                "sample_id": "000123",
                "sample_type": "Other",
            }]).to_excel(path, index=False)

            result = read_sample_table(path)

            self.assertEqual(
                result.iloc[0]["sample_id"],
                "000123",
            )

    def test_export_preserves_general_fields(self):
        sample = SimpleNamespace(
            sample_id="QA-001",
            sample_type="Other",
            organism_name="Organism QA",
            status="qc",
            biobank=None,
            owner=None,
            storage_location="",
            scientific_notes="QA notes",
            notes="",
        )

        row = _sample_to_row(sample)

        self.assertEqual(row["sample_id"], "QA-001")
        self.assertEqual(row["sample_type"], "Other")
        self.assertEqual(
            row["organism_name"],
            "Organism QA",
        )
        self.assertEqual(
            row["scientific_notes"],
            "QA notes",
        )


class ImportValidationV8151Tests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="import-v8151",
        )

    def process(self, rows):
        batch = SampleImportBatch.objects.create(
            uploaded_by=self.user,
            original_file="sample_imports/qa.xlsx",
        )

        with patch(
            "core.services.sample_intake.read_sample_table",
            return_value=pd.DataFrame(rows),
        ):
            import_sample_table(batch)

        batch.refresh_from_db()
        return batch

    def test_duplicate_ids_in_same_file(self):
        batch = self.process([
            {
                "sample_id": "QA-DUP-001",
                "sample_type": "Other",
                "organism_name": "QA",
            },
            {
                "sample_id": "qa-dup-001",
                "sample_type": "Other",
                "organism_name": "QA",
            },
        ])

        self.assertEqual(batch.total_rows, 2)
        self.assertEqual(batch.invalid_rows, 1)

    def test_unknown_type_is_invalid(self):
        batch = self.process([{
            "sample_id": "QA-UNKNOWN",
            "sample_type": "Unknown Material",
            "organism_name": "QA",
        }])

        self.assertEqual(batch.invalid_rows, 1)

    def test_export_collection_header_accepted(self):
        batch = self.process([{
            "sample_id": "QA-COLL-001",
            "sample_type": "Other",
            "organism_name": "QA",
            "collections": "Collection QA",
        }])

        self.assertEqual(
            batch.records.get().collection_name,
            "Collection QA",
        )

    def test_invalid_visibility_is_rejected(self):
        batch = self.process([{
            "sample_id": "QA-PUBLIC-001",
            "sample_type": "Other",
            "organism_name": "QA",
            "is_public": "maybe",
        }])

        self.assertEqual(batch.invalid_rows, 1)

    def test_multiple_collections_require_review(self):
        batch = self.process([{
            "sample_id": "QA-MULTI-001",
            "sample_type": "Other",
            "organism_name": "QA",
            "collection": "A; B",
        }])

        self.assertEqual(batch.invalid_rows, 1)

    def test_missing_header_is_rejected(self):
        batch = SampleImportBatch.objects.create(
            uploaded_by=self.user,
            original_file="sample_imports/qa.xlsx",
        )

        with patch(
            "core.services.sample_intake.read_sample_table",
            return_value=pd.DataFrame([{
                "organism_name": "QA",
            }]),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "Missing required columns",
            ):
                import_sample_table(batch)


class OfficialTemplateV8151Tests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="template-v8151",
        )
        self.client.force_login(self.user)

    def test_excel_template_contract(self):
        response = self.client.get(
            reverse("export_samples_csv"),
            {
                "schema": "template",
                "format": "xlsx",
            },
        )

        self.assertEqual(response.status_code, 200)

        workbook = load_workbook(
            BytesIO(response.content),
            read_only=True,
        )

        self.assertEqual(
            workbook.sheetnames,
            [
                "samples",
                "field_dictionary",
                "allowed_values",
                "instructions",
            ],
        )

        with TemporaryDirectory() as root:
            path = Path(root) / "template.xlsx"
            path.write_bytes(response.content)

            parsed = read_sample_table(path)

            self.assertEqual(len(parsed), 0)
            self.assertIn("sample_id", parsed.columns)
            self.assertIn("sample_type", parsed.columns)
            self.assertIn("collection", parsed.columns)

    def test_csv_template(self):
        response = self.client.get(
            reverse("export_samples_csv"),
            {
                "schema": "template",
                "format": "csv",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sample_id", response.content)
        self.assertIn(b"sample_type", response.content)

    def test_download_button(self):
        response = self.client.get(
            reverse("samples_import")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Download official import template",
        )
