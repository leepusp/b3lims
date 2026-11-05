import json
import shutil
import subprocess
import unittest
from pathlib import Path

from django.test import SimpleTestCase

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "static/internal/storage/storage_v814.js"
)


def run_node(expression):
    code = (
        f"const m = require({json.dumps(str(SCRIPT))});"
        f"console.log(JSON.stringify({expression}));"
    )
    out = subprocess.run(
        ["node", "-e", code], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class OccupancyRuleTests(SimpleTestCase):
    def test_slot_names_follow_the_position_map(self):
        self.assertEqual(run_node('m.gridSlot("a1", 9, 9)'), "A1")
        self.assertEqual(run_node('m.gridSlot(" b7 ", 9, 9)'), "B7")
        self.assertEqual(run_node('m.gridSlot("B07", 9, 9)'), "B7")
        self.assertEqual(run_node('m.gridSlot("B00", 9, 9)'), "")
        self.assertEqual(run_node('m.gridSlot("A10", 9, 9)'), "")
        self.assertEqual(run_node('m.gridSlot("J1", 9, 9)'), "")
        self.assertEqual(run_node('m.gridSlot("1A", 9, 9)'), "")
        self.assertEqual(run_node('m.gridSlot("", 9, 9)'), "")

    def test_usage_counts_distinct_cells_and_off_grid_samples(self):
        usage = run_node(
            'm.gridUsage(9, 9, ["A1", "a1", "B2", "ZZ", "", "Tube 5"])'
        )
        self.assertEqual(usage, {"used": 2, "offGrid": 3})

    def test_empty_location_has_no_usage(self):
        self.assertEqual(
            run_node("m.gridUsage(9, 9, [])"), {"used": 0, "offGrid": 0}
        )
