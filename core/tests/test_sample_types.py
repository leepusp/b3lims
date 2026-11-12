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
