"""Drawing of a Sample's location on the Sample detail and edit pages."""

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
from core.services.storage_sample_drawing import build_sample_storage_drawings

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static/internal/samples/sample_storage_drawing_v816.js"
STORAGE_JS = (ROOT / "static/internal/storage/storage_v814.js").read_text()


def make(identifier, owner):
    return Sample.objects.create(
        sample_id=identifier, sample_type="Other", organism_name=identifier,
        owner=owner, status="available", is_active=True, is_public=False,
    )


class SampleDrawingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="b3-draw-owner")
        cls.other = User.objects.create_user(username="b3-draw-other")
        ws = StorageWorkspace.objects.create(
            name="Draw ws", scope="personal", owner=cls.owner
        )
        cls.box = StorageLocation.objects.create(
            name="Draw box", location_type="box", workspace=ws
        )
        StorageLocationLayoutV8146C3.objects.create(
            location=cls.box, organization="grid", rows=3, columns=3
        )
        cls.room = StorageLocation.objects.create(
            name="Draw room", location_type="room", workspace=ws
        )
        cls.mine = make("DRAW-MINE", cls.owner)
        cls.neighbour = make("DRAW-NEIGH", cls.owner)
        cls.in_room = make("DRAW-ROOM", cls.owner)
        SampleStorageAssignment.objects.create(
            sample=cls.mine, location=cls.box, position="B2",
            is_primary=True, rank=1, status="active")
        SampleStorageAssignment.objects.create(
            sample=cls.neighbour, location=cls.box, position="A1",
            is_primary=True, rank=1, status="active")
        SampleStorageAssignment.objects.create(
            sample=cls.in_room, location=cls.room, position="",
            is_primary=True, rank=1, status="active")

    def test_builder_lists_layout_and_neighbours_only(self):
        entry = build_sample_storage_drawings(self.mine, self.owner)[0]
        self.assertEqual(entry["organization"], "grid")
        self.assertEqual(entry["position"], "B2")
        self.assertEqual(entry["others"], ["A1"])
        self.assertTrue(entry["can_move"])

    def test_free_location_has_no_drawing(self):
        entry = build_sample_storage_drawings(self.in_room, self.owner)[0]
        self.assertEqual(entry["organization"], "free")
        self.assertEqual(entry["others"], [])

    def test_foreign_user_gets_nothing(self):
        self.assertEqual(
            build_sample_storage_drawings(self.mine, self.other), []
        )

    def test_detail_and_edit_pages_carry_the_drawing(self):
        self.client.force_login(self.owner)
        for name in ("sample_detail", "sample_edit"):
            response = self.client.get(reverse(name, args=[self.mine.pk]))
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, 'id="b3-sample-drawings"')
            self.assertContains(response, "sample_storage_drawing_v816.js")


def run(expression):
    code = (
        f"const m=require({json.dumps(str(JS))});"
        f"console.log(JSON.stringify({expression}));"
    )
    out = subprocess.run(
        [shutil.which("node"), "-e", code],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


class DrawingHelpersTests(SimpleTestCase):
    def test_canonical(self):
        grid = '{organization:"grid",rows:3,columns:4}'
        slots = '{organization:"slots",slots:["Door 1"]}'
        self.assertEqual(run(f'm.canonical({grid},"b02")'), "B2")
        self.assertEqual(run(f'm.canonical({grid},"D1")'), "")
        self.assertEqual(run(f'm.canonical({slots},"door  1")'), "Door 1")

    def test_storage_page_understands_deep_links(self):
        self.assertIn('params.get("move_assignment")', STORAGE_JS)
        self.assertIn('params.get("location")', STORAGE_JS)
