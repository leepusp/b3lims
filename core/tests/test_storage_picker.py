"""Destination picker: pure helpers and the page contract."""

import json
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "static/internal/storage/storage_picker_v815.js"
TEMPLATE = ROOT / "interfaces/internal/storage/index_v814.html"
MAIN = ROOT / "static/internal/storage/storage_v814.js"


def run_node(expression):
    node = shutil.which("node")
    if not node:
        raise AssertionError("node is required")
    code = (
        f"const m = require({json.dumps(str(SCRIPT))});"
        f"console.log(JSON.stringify({expression}));"
    )
    out = subprocess.run(
        [node, "-e", code], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


class PickerHelpersTests(SimpleTestCase):

    GRID = '{kind:"grid", rows:3, columns:4}'
    SLOTS = '{kind:"slots", slots:["Door 1","Door 2","Door 3"]}'

    def test_grid_positions_are_row_major(self):
        names = run_node(f"m.allPositions({self.GRID})")

        self.assertEqual(len(names), 12)
        self.assertEqual(names[:5], ["A1", "A2", "A3", "A4", "B1"])
        self.assertEqual(names[-1], "C4")

    def test_slots_keep_their_order(self):
        self.assertEqual(
            run_node(f"m.allPositions({self.SLOTS})"),
            ["Door 1", "Door 2", "Door 3"],
        )

    def test_free_layout_has_no_positions(self):
        self.assertEqual(run_node('m.allPositions({kind:"free"})'), [])

    def test_canonical_position(self):
        self.assertEqual(run_node(f'm.canonicalPosition({self.GRID}, "b07")'), "")
        self.assertEqual(run_node(f'm.canonicalPosition({self.GRID}, "b02")'), "B2")
        self.assertEqual(run_node(f'm.canonicalPosition({self.GRID}, "D1")'), "")
        self.assertEqual(
            run_node(f'm.canonicalPosition({self.SLOTS}, "door 2")'), "Door 2"
        )
        self.assertEqual(
            run_node(f'm.canonicalPosition({self.SLOTS}, "Door 9")'), ""
        )

    def test_free_run_skips_used_positions(self):
        order = ["A1", "A2", "A3", "A4", "B1"]

        self.assertEqual(
            run_node(
                f"m.freeRun({json.dumps(order)}, new Set(['A3']), 'A2', 3)"
            ),
            ["A2", "A4", "B1"],
        )

    def test_free_run_stops_at_the_end_and_refuses_used_start(self):
        order = ["A1", "A2", "A3"]

        self.assertEqual(
            run_node(f"m.freeRun({json.dumps(order)}, new Set(), 'A2', 5)"),
            ["A2", "A3"],
        )
        self.assertEqual(
            run_node(
                f"m.freeRun({json.dumps(order)}, new Set(['A2']), 'A2', 2)"
            ),
            [],
        )


class PickerPageContractTests(SimpleTestCase):

    def test_storage_page_loads_picker_before_the_main_script(self):
        html = TEMPLATE.read_text()

        self.assertIn("storage_picker_v815.js", html)
        self.assertLess(
            html.index("storage_picker_v815.js"),
            html.index("storage_v814.js'"),
        )
        self.assertIn("data-b3s-preview-samples", html)

    def test_moves_use_the_picker_and_the_server_preview(self):
        source = MAIN.read_text()

        for needle in (
            "B3StoragePicker.open",
            'mode: "node"',
            'mode: "place"',
            "preview_bulk_samples",
            "preview_sample",
            "b3sPreviewSamples",
        ):
            self.assertIn(needle, source)
