from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from core.models import SampleImportBatch
from core.services import sample_tables as tables
from core.services.sample_intake import import_sample_table, read_sample_table


class NormalizeTests(TestCase):
    def col(self, key):
        return tables.by_key()[key]

    def test_numbers(self):
        self.assertEqual(tables.normalize_value(self.col("genome_size_bp"), "168903.0"), ("168903", ""))
        self.assertIn("whole number", tables.normalize_value(self.col("genome_size_bp"), "big")[1])
        self.assertIn("whole number", tables.normalize_value(self.col("genome_size_bp"), "12.5")[1])
        self.assertIn("1 or more", tables.normalize_value(self.col("genome_size_bp"), "0")[1])
        self.assertEqual(tables.normalize_value(self.col("temp_C"), "37,5"), ("37.5", ""))
        self.assertIn("range", tables.normalize_value(self.col("temp_C"), "900")[1])

    def test_choices_booleans_dates_lists(self):
        self.assertEqual(tables.normalize_value(self.col("lifestyle"), "LYTIC"), ("lytic", ""))
        self.assertIn("not one of", tables.normalize_value(self.col("lifestyle"), "temperate")[1])
        self.assertEqual(tables.normalize_value(self.col("temperature_condition"), "on ice"), ("on ice", ""))
        self.assertEqual(tables.normalize_value(self.col("is_empty_vector"), "Sim"), ("true", ""))
        self.assertIn("yes or no", tables.normalize_value(self.col("is_empty_vector"), "maybe")[1])
        self.assertEqual(tables.normalize_value(self.col("expected_arrival_date"), "2026-12-01 00:00:00"), ("2026-12-01", ""))
        self.assertEqual(tables.normalize_value(self.col("expected_arrival_date"), "01/12/2026"), ("2026-12-01", ""))
        self.assertIn("date", tables.normalize_value(self.col("expected_arrival_date"), "soon")[1])
        self.assertEqual(tables.normalize_value(self.col("resistance_markers"), "AmpR; KanR,  CmR"), ("AmpR, KanR, CmR", ""))

    def test_columns_per_type(self):
        keys = {t: {c.key for c in tables.columns_for(t)} for t in tables.SAMPLE_TYPES}

        self.assertIn("resistance_markers", keys[tables.BACTERIUM])
        self.assertNotIn("lifestyle", keys[tables.BACTERIUM])
        self.assertIn("lifestyle", keys[tables.PHAGE])
        self.assertIn("backbone_name", keys[tables.PLASMID])
        self.assertNotIn("genus", keys[tables.OTHER])
        self.assertTrue(keys[tables.PHAGE] | keys[tables.PLASMID] <= {c.key for c in tables.columns_for(None)})


class TemplateAndImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tables-user", password="x")
        self.client.force_login(self.user)

    def download(self, **params):
        return self.client.get(reverse("export_samples_csv"), {"schema": "template", "format": "xlsx", **params})

    def test_each_type_has_its_own_columns_validation_and_example(self):
        phage = load_workbook(BytesIO(self.download(type="phage").content))
        headers = [c.value for c in phage["samples"][1]]

        self.assertIn("lifestyle", headers)
        self.assertNotIn("resistance_markers", headers)
        self.assertEqual(phage["samples"]["B2"].value, "Phage (Virus)")

        validations = {str(v.sqref): v.type for v in phage["samples"].data_validations.dataValidation}
        letter = lambda key: __import__("openpyxl").utils.get_column_letter(headers.index(key) + 1)  # noqa: E731

        self.assertEqual(validations[f"{letter('lifestyle')}2:{letter('lifestyle')}201"], "list")
        self.assertEqual(validations[f"{letter('genome_size_bp')}2:{letter('genome_size_bp')}201"], "whole")
        self.assertEqual(validations[f"{letter('temp_C')}2:{letter('temp_C')}201"], "decimal")
        self.assertEqual(validations[f"{letter('expected_arrival_date')}2:{letter('expected_arrival_date')}201"], "date")
        self.assertEqual(phage["example"]["B2"].value, "Phage (Virus)")
        self.assertEqual({r[0].value for r in phage["field_dictionary"].iter_rows(min_row=2)} >= {"lifestyle", "genome_size_bp"}, True)

        bacterium = [c.value for c in load_workbook(BytesIO(self.download(type="bacterium").content))["samples"][1]]

        self.assertIn("resistance_markers", bacterium)
        self.assertNotIn("lifestyle", bacterium)
        self.assertEqual(self.download(type="nope").status_code, 400)

    def test_template_example_row_imports_cleanly(self):
        for slug, sample_type in tables.TYPE_SLUGS.items():
            sheet = load_workbook(BytesIO(self.download(type=slug).content))["example"]
            header = [c.value for c in sheet[1]]
            row = dict(zip(header, [c.value for c in sheet[2]]))
            row["sample_id"] = f"IMPORT-{slug}"

            with TemporaryDirectory() as root:
                path = Path(root) / "t.csv"
                pd.DataFrame([row]).to_csv(path, index=False)
                batch = SampleImportBatch.objects.create(uploaded_by=self.user, original_file=ContentFile(path.read_bytes(), name="t.csv"), original_filename="t.csv")
                import_sample_table(batch)

            record = batch.records.get()

            self.assertEqual(record.validation_errors, [], (slug, record.validation_errors))
            self.assertEqual(record.sample_type, sample_type)

    def import_rows(self, rows):
        with TemporaryDirectory() as root:
            path = Path(root) / "t.csv"
            pd.DataFrame(rows).to_csv(path, index=False)
            batch = SampleImportBatch.objects.create(uploaded_by=self.user, original_file=ContentFile(path.read_bytes(), name="t.csv"), original_filename="t.csv")
            import_sample_table(batch)

        return batch

    def test_typed_columns_are_validated_and_normalised(self):
        batch = self.import_rows([
            {"sample_id": "T-1", "sample_type": "phage", "phage_name": "T4", "genome_size_bp": "abc", "lifestyle": "Lytic", "genus": "Tequatrovirus"},
            {"sample_id": "T-2", "sample_type": "Phage (Virus)", "phage_name": "T7", "genome_size_bp": "39937.0", "lifestyle": "LYTIC", "temp_C": "37,5", "resistance_markers": "AmpR"},
            {"sample_id": "T-3", "sample_type": "Plasmid", "backbone_name": "pET28a", "is_empty_vector": "maybe", "backbone_resistance_markers": "KanR;CmR"},
        ])
        first, second, third = batch.records.order_by("row_number")

        self.assertTrue(any("genome_size_bp must be a whole number" in e for e in first.validation_errors))
        self.assertEqual(second.validation_errors, [])
        self.assertEqual(second.normalized_data["genome_size_bp"], "39937")
        self.assertEqual(second.normalized_data["lifestyle"], "lytic")
        self.assertEqual(second.normalized_data["temp_C"], "37.5")
        self.assertEqual(second.normalized_data["resistance_markers"], "")
        self.assertTrue(any("resistance_markers does not apply" in w for w in second.validation_warnings))
        self.assertTrue(any("yes or no" in e for e in third.validation_errors))

    def test_unknown_columns_are_reported(self):
        batch = self.import_rows([{"sample_id": "U-1", "sample_type": "Other", "organism_name": "Soil", "colour": "red"}])

        self.assertIn("colour", batch.notes)

    def test_typed_template_with_untouched_rows_is_accepted(self):
        content = self.download(type="plasmid").content

        with TemporaryDirectory() as root:
            path = Path(root) / "t.xlsx"
            path.write_bytes(content)
            frame = read_sample_table(path)

        self.assertEqual(len(frame.dropna(how="all")), len(frame))

    def test_import_page_offers_the_types(self):
        page = self.client.get(reverse("samples_import")).content.decode()

        for label in ("Bacterium (Host)", "Phage (Virus)", "Plasmid", "All types in one table"):
            self.assertIn(label, page)


class TypedExportTests(TestCase):
    def test_export_of_one_type_uses_the_template_columns(self):
        from core.models import Phage

        user = get_user_model().objects.create_user("export-user", is_superuser=True, is_staff=True)
        Phage.objects.create(sample_id="EXP-P-1", sample_type="Phage (Virus)", organism_name="T4", owner=user, phage_name="T4", lifestyle="lytic", genome_size_bp=168903, is_public=True)
        self.client.force_login(user)

        response = self.client.get(reverse("export_samples_csv"), {"format": "csv", "sample_type": "Phage (Virus)"})
        frame = pd.read_csv(BytesIO(response.content), dtype=str, keep_default_na=False)

        self.assertEqual(list(frame.columns), [c.key for c in tables.columns_for(tables.PHAGE)])
        self.assertEqual(frame.loc[0, "lifestyle"], "lytic")
        self.assertEqual(frame.loc[0, "genome_size_bp"], "168903")
        self.assertEqual(frame.loc[0, "is_public"], "true")
