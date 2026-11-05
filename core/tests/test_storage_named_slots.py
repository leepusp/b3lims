"""Named compartments (doors, drawers, shelves) as a storage layout."""

import json
import shutil
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.services.storage_layout_position import position_for_layout
from core.models.samples.storage import (
    StorageLocation,
    StorageLocationLayoutV8146C3,
    StorageWorkspace,
    clean_slot_labels,
)

ROOT = Path(__file__).resolve().parents[1]


class CleanSlotLabelsTests(SimpleTestCase):

    def test_trims_and_keeps_order(self):
        self.assertEqual(
            clean_slot_labels(["  Door   1 ", "Door 2"]),
            ["Door 1", "Door 2"],
        )

    def test_rejects_empty_repeated_and_unsafe_names(self):
        for bad in (
            [],
            [""],
            ["A", "a"],
            ["A>B"],
            ["A,B"],
            ["x" * 41],
            ["bell\x07"],
            [f"S{i}" for i in range(41)],
            "Door 1",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    clean_slot_labels(bad)


class NamedSlotsViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username="slots-owner"
        )
        cls.workspace = StorageWorkspace.objects.create(
            name="Slots workspace", scope="personal", owner=cls.owner
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("storage_location_create_with_layout_v8146c3")

    def post(self, **changes):
        data = {
            "action": "create_location",
            "workspace_id": str(self.workspace.pk),
            "parent_id": "",
            "name": "Freezer door cabinet",
            "location_type": "other",
            "rank": "1",
            "organization": "slots",
            "slot_direction": "row",
            "slot_label": ["Door 1", "Door 2"],
        }
        data.update(changes)
        return self.client.post(self.url, data)

    def test_creates_compartments(self):
        self.post()
        layout = StorageLocationLayoutV8146C3.objects.get()

        self.assertEqual(layout.organization, "slots")
        self.assertEqual(layout.slot_labels, ["Door 1", "Door 2"])
        self.assertEqual(layout.slot_direction, "row")
        self.assertEqual((layout.rows, layout.columns), (0, 0))
        self.assertEqual(layout.capacity, 2)
        self.assertEqual(json.loads(layout.slot_labels_json), ["Door 1", "Door 2"])

    def test_repeated_names_create_nothing(self):
        self.post(slot_label=["Door 1", "door 1"])

        self.assertFalse(StorageLocation.objects.exists())
        self.assertFalse(StorageLocationLayoutV8146C3.objects.exists())

    def test_missing_names_create_nothing(self):
        self.post(slot_label=[])

        self.assertFalse(StorageLocation.objects.exists())

    def test_invalid_direction_creates_nothing(self):
        self.post(slot_direction="diagonal")

        self.assertFalse(StorageLocation.objects.exists())

    def test_grid_cannot_carry_compartments(self):
        layout = StorageLocationLayoutV8146C3(
            location=StorageLocation.objects.create(
                name="Box", workspace=self.workspace, location_type="box"
            ),
            organization="grid",
            rows=2,
            columns=2,
            slot_labels=["Door 1"],
        )

        with self.assertRaises(ValidationError):
            layout.full_clean()

    def test_grid_still_works(self):
        self.post(organization="grid", rows="8", columns="12", slot_label=[])
        layout = StorageLocationLayoutV8146C3.objects.get()

        self.assertEqual(layout.capacity, 96)
        self.assertEqual(layout.slot_labels, [])


class SlotNamesScriptTests(SimpleTestCase):

    def run_node(self, expression):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not available")
        script = ROOT / "static/internal/storage/storage_layout_v8146c3.js"
        code = (
            f"const m = require({json.dumps(str(script))});"
            f"console.log(JSON.stringify({expression}));"
        )
        out = subprocess.run(
            [node, "-e", code], capture_output=True, text=True, check=True
        )
        return json.loads(out.stdout)

    def test_default_names(self):
        self.assertEqual(
            self.run_node('m.slotNames("Door", 3)'),
            ["Door 1", "Door 2", "Door 3"],
        )

    def test_resize_keeps_renamed(self):
        self.assertEqual(
            self.run_node('m.resizeNames(["Reagents","Door 2"], "Door", 3)'),
            ["Reagents", "Door 2", "Door 3"],
        )
        self.assertEqual(
            self.run_node('m.resizeNames(["Reagents","Door 2"], "Door", 1)'),
            ["Reagents"],
        )

    def test_reword_changes_only_automatic_names(self):
        self.assertEqual(
            self.run_node('m.rewordNames(["Reagents","Door 2"], "Door", "Drawer")'),
            ["Reagents", "Drawer 2"],
        )


class PositionForLayoutTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="pos-owner")
        cls.ws = StorageWorkspace.objects.create(
            name="Pos", scope="personal", owner=cls.owner
        )

    def location(self, name, **layout):
        loc = StorageLocation.objects.create(
            name=name, workspace=self.ws, location_type="other"
        )
        if layout:
            StorageLocationLayoutV8146C3.objects.create(location=loc, **layout)
        return loc

    def test_free_and_unlaid_out_locations_keep_the_text(self):
        self.assertEqual(position_for_layout(self.location("none"), "Left side"), "Left side")
        self.assertEqual(
            position_for_layout(self.location("free", organization="free"), "x1"), "x1"
        )

    def test_grid_accepts_slots_inside_and_canonicalises(self):
        box = self.location("g", organization="grid", rows=3, columns=4)

        self.assertEqual(position_for_layout(box, "b02"), "B2")
        self.assertEqual(position_for_layout(box, "C4"), "C4")

    def test_grid_rejects_outside_slots_and_free_text(self):
        box = self.location("g2", organization="grid", rows=3, columns=4)

        for bad in ("D1", "A5", "A0", "Door 1"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                position_for_layout(box, bad)

    def test_slots_match_by_name_ignoring_case(self):
        cabinet = self.location(
            "c", organization="slots", slot_labels=["Door 1", "Door 2"]
        )

        self.assertEqual(position_for_layout(cabinet, "door  2"), "Door 2")
        with self.assertRaises(ValidationError):
            position_for_layout(cabinet, "Door 3")


class CatalogCarriesTheDrawingTests(TestCase):

    def test_catalog_lists_layout_and_occupied_positions(self):
        from core.models import Sample
        from core.models.samples.storage import SampleStorageAssignment
        from core.services.storage_anchor_catalog_v8 import (
            build_storage_anchor_catalog,
        )

        user = get_user_model().objects.create_user(username="cat-owner")
        ws = StorageWorkspace.objects.create(
            name="Cat", scope="personal", owner=user
        )
        room = StorageLocation.objects.create(
            name="Room", workspace=ws, location_type="room"
        )
        cabinet = StorageLocation.objects.create(
            name="Cabinet", workspace=ws, location_type="other", parent=room
        )
        StorageLocationLayoutV8146C3.objects.create(
            location=cabinet,
            organization="slots",
            slot_labels=["Door 1", "Door 2"],
            slot_direction="row",
        )
        sample = Sample.objects.create(
            sample_id="CAT-1",
            sample_type="Other",
            organism_name="Catalog test",
            owner=user,
            status="available",
            aliquot_count=1,
            is_active=True,
            storage_location="",
        )
        SampleStorageAssignment.objects.create(
            sample=sample, location=cabinet, position="Door 2", status="active"
        )

        rows = {r["name"]: r for r in build_storage_anchor_catalog(user=user)}

        self.assertEqual(rows["Room"]["organization"], "free")
        self.assertEqual(rows["Cabinet"]["organization"], "slots")
        self.assertEqual(rows["Cabinet"]["slots"], ["Door 1", "Door 2"])
        self.assertEqual(rows["Cabinet"]["direction"], "row")
        self.assertEqual(rows["Cabinet"]["occupied"], ["Door 2"])
