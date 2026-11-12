from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.sample_type import SampleType
from core.services import sample_types

FIELDS = (
    "Passage number | integer | required\n"
    "Mycoplasma status | choice | required | negative, positive, untested\n"
    "Thawed on | date\n"
)


class SampleTypeServiceTests(TestCase):
    def test_field_lines_become_a_schema_and_back(self):
        fields = sample_types.parse_fields(FIELDS)

        self.assertEqual([f["key"] for f in fields], ["passage_number", "mycoplasma_status", "thawed_on"])
        self.assertTrue(fields[0]["required"])
        self.assertEqual(fields[1]["choices"], ["negative", "positive", "untested"])
        self.assertEqual(sample_types.parse_fields(sample_types.fields_to_text(fields)), fields)

    def test_mistakes_are_explained(self):
        for text in ("Size | meters", "Status | choice | required", "A\nA"):
            with self.assertRaises(sample_types.SampleTypeError):
                sample_types.parse_fields(text)

    def test_values_are_checked_against_the_schema(self):
        kind = SampleType.objects.create(name="Cell line", slug="cell-line", fields=sample_types.parse_fields(FIELDS))
        good = sample_types.read_values(kind, {"tf_passage_number": "12", "tf_mycoplasma_status": "negative"})

        self.assertEqual(good, {"passage_number": 12, "mycoplasma_status": "negative"})

        with self.assertRaises(sample_types.SampleTypeError):
            sample_types.read_values(kind, {"tf_passage_number": "twelve", "tf_mycoplasma_status": "negative"})

        with self.assertRaises(sample_types.SampleTypeError):
            sample_types.read_values(kind, {"tf_passage_number": "3"})


class SampleTypeScreensTests(TestCase):
    def setUp(self):
        model = get_user_model()
        self.admin = model.objects.create_user("boss", password="pw-12345678", is_staff=True)
        self.member = model.objects.create_user("ana", password="pw-12345678")

    def test_only_administrators_create_types(self):
        self.client.force_login(self.member)
        denied = self.client.post(reverse("sample_types"), {"name": "Cell line", "fields": FIELDS})

        self.assertEqual(denied.status_code, 403)
        self.assertFalse(SampleType.objects.exists())

        self.client.force_login(self.admin)
        saved = self.client.post(reverse("sample_types"), {"name": "Cell line", "id_prefix": "cel", "fields": FIELDS})

        self.assertEqual(saved.status_code, 302)
        kind = SampleType.objects.get()
        self.assertEqual(kind.id_prefix, "CEL-")
        self.assertEqual(len(kind.fields), 3)

    def test_built_in_names_are_refused(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("sample_types"), {"name": "plasmid", "fields": ""})

        self.assertFalse(SampleType.objects.exists())

    def test_a_sample_of_a_new_type_is_registered_with_its_values(self):
        SampleType.objects.create(name="Cell line", slug="cell-line", id_prefix="CEL-",
                                  fields=sample_types.parse_fields(FIELDS))
        self.client.force_login(self.admin)

        page = self.client.get(reverse("sample_add"))
        self.assertContains(page, 'value="Cell line"')
        self.assertContains(page, "Passage number")

        post = {
            "action": "add_sample", "sample_id": "CEL-2026-001", "sample_type": "Cell line",
            "custom_type_name": "HEK293", "tf_passage_number": "7", "tf_mycoplasma_status": "negative",
            "biosafety_level": "", "aliquot_count": "1", "owner": str(self.admin.pk),
            "research_group": "", "storage_location": "", "scientific_notes": "", "collaborator": "",
        }
        done = self.client.post(reverse("sample_add"), post)

        self.assertEqual(done.status_code, 302)
        sample = Sample.objects.get(sample_id="CEL-2026-001")
        self.assertEqual(sample.sample_type, "Cell line")
        self.assertEqual(sample.organism_name, "HEK293")
        self.assertEqual(sample.type_data, {"passage_number": 7, "mycoplasma_status": "negative"})

        missing = self.client.post(reverse("sample_add"), {**post, "sample_id": "CEL-2026-002", "tf_passage_number": ""})
        self.assertFalse(Sample.objects.filter(sample_id="CEL-2026-002").exists())
        self.assertNotEqual(missing.status_code, 500)


class SampleTypeDisplayTests(TestCase):
    def test_extra_fields_appear_on_the_sample_page(self):
        admin = get_user_model().objects.create_user("boss2", password="pw-12345678", is_staff=True)
        SampleType.objects.create(name="Cell line", slug="cell-line", fields=sample_types.parse_fields(FIELDS))
        sample = Sample.objects.create(
            sample_id="CEL-9", sample_type="Cell line", organism_name="HEK293", owner=admin,
            type_data={"passage_number": 7}, is_active=True, status="available",
        )
        self.client.force_login(admin)
        page = self.client.get(reverse("sample_qr_scan", args=[sample.uuid]))

        self.assertContains(page, "Passage number")
        self.assertContains(page, "7")
        self.assertContains(self.client.get(reverse("samples_list")), "Sample types")


class FieldTableEditorTests(TestCase):
    def test_the_page_offers_a_table_and_posts_the_lines_it_builds(self):
        admin = get_user_model().objects.create_user("boss3", password="pw-12345678", is_staff=True)
        self.client.force_login(admin)

        page = self.client.get(reverse("sample_types"))
        self.assertContains(page, 'id="fieldsTable"')
        self.assertContains(page, "Value type")

        self.client.post(reverse("sample_types"), {
            "name": "Tissue", "id_prefix": "TIS-",
            "fields": "Site | text | required |\nGrade | choice | | I, II, III",
        })
        kind = SampleType.objects.get(name="Tissue")
        self.assertEqual([f["key"] for f in kind.fields], ["site", "grade"])

        edit = self.client.get(reverse("sample_type_edit", args=[kind.pk]))
        self.assertContains(edit, 'value="Grade"')
        self.assertContains(edit, 'value="I, II, III"')


class SampleTypeImportExportTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.admin = get_user_model().objects.create_user("boss4", password="pw-12345678", is_staff=True)
        self.kind = SampleType.objects.create(
            name="Cell line", slug="cell-line", id_prefix="CEL-", has_organism=True,
            fields=sample_types.parse_fields(FIELDS),
        )
        self.client.force_login(self.admin)

    def test_reserved_field_names_are_refused(self):
        self.client.post(reverse("sample_types"), {"name": "Tissue", "fields": "Genus | text\nSpecies | text"})

        self.assertFalse(SampleType.objects.filter(name="Tissue").exists())

    def test_the_template_for_the_type_has_its_columns(self):
        from core.services import sample_tables

        keys = [c.key for c in sample_tables.columns_for("Cell line")]

        self.assertIn("passage_number", keys)
        self.assertIn("mycoplasma_status", keys)
        self.assertNotIn("genus", keys)
        self.assertEqual(sample_tables.type_for_slug("cell-line"), "Cell line")
        self.assertEqual(sample_tables.prefix_of("Cell line"), "CEL-")

        response = self.client.get(reverse("export_samples_csv"), {"schema": "template", "type": "cell-line", "format": "csv"})
        header = response.content.decode().splitlines()[0]

        self.assertEqual(response.status_code, 200)
        self.assertIn("passage_number", header)

    def test_an_uploaded_table_is_validated_with_the_type_columns(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile

        good = (
            "sample_id,sample_type,organism_name,passage_number,mycoplasma_status\n"
            "CEL-1,Cell line,HEK293,5,negative\n"
            "CEL-2,Cell line,HeLa,abc,negative\n"
        )
        done = self.client.post(
            reverse("samples_import"),
            {"sample_table": SimpleUploadedFile("cells.csv", good.encode(), content_type="text/csv")},
        )

        self.assertIn(done.status_code, (200, 302))

        from core.models.samples.intake import SampleIntakeRecord

        rows = {r.imported_sample_id: r for r in SampleIntakeRecord.objects.all()}

        self.assertEqual(rows["CEL-1"].validation_errors, [])
        self.assertEqual(rows["CEL-1"].normalized_data["passage_number"], "5")
        self.assertTrue(any("passage_number" in e for e in rows["CEL-2"].validation_errors))

    def test_export_includes_the_extra_fields(self):
        Sample.objects.create(
            sample_id="CEL-7", sample_type="Cell line", organism_name="HEK293", owner=self.admin,
            type_data={"passage_number": 7, "mycoplasma_status": "negative"}, is_active=True, status="available",
        )
        response = self.client.get(reverse("export_samples_csv"), {"schema": "standard", "sample_type": "Cell line", "format": "csv"})
        text = response.content.decode()

        self.assertIn("passage_number", text.splitlines()[0])
        self.assertIn("negative", text)
