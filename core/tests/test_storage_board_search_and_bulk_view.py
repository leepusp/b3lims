"""Sample search for the drawing, and the drawing on the bulk move page."""

import json
import shutil
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageLocationLayoutV8146C3,
    StorageWorkspace,
)

ROOT = Path(__file__).resolve().parents[1]
BULK_JS = ROOT / "static/internal/samples/bulk_storage_v8148.js"
BULK_TEMPLATE = ROOT / "interfaces/internal/samples/bulk_storage_v8148.html"


def make_sample(identifier, owner):
    return Sample.objects.create(
        sample_id=identifier, sample_type="Other", organism_name=identifier,
        owner=owner, status="available", is_active=True, is_public=False,
    )


class BoardSearchAndBulkViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="b3-board-owner")
        cls.other = User.objects.create_user(username="b3-board-other")
        ws = StorageWorkspace.objects.create(
            name="Board ws", scope="personal", owner=cls.owner
        )
        cls.cabinet = StorageLocation.objects.create(
            name="Door cabinet", location_type="other", workspace=ws
        )
        StorageLocationLayoutV8146C3.objects.create(
            location=cls.cabinet, organization="slots",
            slot_labels=["Door 1", "Door 2"], slot_direction="row",
        )
        cls.placed = make_sample("BRD-PLACED-1", cls.owner)
        cls.loose = make_sample("BRD-LOOSE-2", cls.owner)
        cls.foreign = make_sample("BRD-FOREIGN-3", cls.other)
        SampleStorageAssignment.objects.create(
            sample=cls.placed, location=cls.cabinet, position="Door 2",
            is_primary=True, rank=1, status="active",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_search_finds_placed_and_unplaced_but_not_foreign(self):
        response = self.client.get(
            reverse("storage_sample_search"), {"q": "BRD-"}
        )
        self.assertEqual(response.status_code, 200)
        found = {item["sample"]: item for item in response.json()["results"]}
        self.assertIn("BRD-LOOSE-2", found)
        self.assertEqual(found["BRD-LOOSE-2"]["where"], "")
        self.assertIn("Door 2", found["BRD-PLACED-1"]["where"])
        self.assertNotIn("BRD-FOREIGN-3", found)

    def test_short_query_returns_nothing(self):
        response = self.client.get(reverse("storage_sample_search"), {"q": "B"})
        self.assertEqual(response.json()["results"], [])

    def test_search_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("storage_sample_search"), {"q": "BRD"})
        self.assertEqual(response.status_code, 302)

    def test_bulk_page_carries_layout_of_destinations(self):
        response = self.client.post(
            reverse("sample_bulk_storage"),
            {"action": "choose", "sample_ids": [self.loose.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="b3-bulk-catalog"')
        self.assertContains(response, "bulk_storage_v8148.js")
        self.assertContains(response, "Door 1")
        self.assertNotContains(response, 'pattern="[A-Za-z]+[0-9]+"')

    def test_named_compartment_goes_through_preview(self):
        response = self.client.post(
            reverse("sample_bulk_storage"),
            {
                "action": "preview",
                "sample_ids": [self.loose.pk],
                "destination_id": self.cabinet.pk,
                f"position_{self.loose.pk}": "door 1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Door 1")


def run(expression):
    node = shutil.which("node")
    code = (
        f"const m=require({json.dumps(str(BULK_JS))});"
        f"console.log(JSON.stringify({expression}));"
    )
    out = subprocess.run(
        [node, "-e", code], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


class BulkDrawingHelpersTests(SimpleTestCase):
    GRID = '{organization:"grid",rows:3,columns:4}'
    SLOTS = '{organization:"slots",slots:["Door 1","Door 2"]}'

    def test_grid_canonical(self):
        self.assertEqual(run(f'm.canonical({self.GRID},"b07")'), "")
        self.assertEqual(run(f'm.canonical({self.GRID},"b02")'), "B2")
        self.assertEqual(run(f'm.canonical({self.GRID},"D1")'), "")
        self.assertEqual(run(f'm.canonical({self.GRID},"A5")'), "")

    def test_slot_canonical_ignores_case_and_spaces(self):
        self.assertEqual(run(f'm.canonical({self.SLOTS},"  door   2 ")'), "Door 2")
        self.assertEqual(run(f'm.canonical({self.SLOTS},"Door 9")'), "")

    def test_names_row_major(self):
        self.assertEqual(run(f"m.names({self.GRID})")[:5], ["A1", "A2", "A3", "A4", "B1"])

    def test_template_has_drawing_hooks_and_no_a1_pattern(self):
        text = BULK_TEMPLATE.read_text()
        self.assertIn('id="bulkDrawingCanvas"', text)
        self.assertIn("data-bulk-position", text)
        self.assertNotIn("[A-Za-z]+[0-9]+", text)
