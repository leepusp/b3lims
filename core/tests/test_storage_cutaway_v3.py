from pathlib import Path

from django.test import SimpleTestCase


CORE = Path(__file__).resolve().parents[1]


class StorageCutawayV3ContractTests(SimpleTestCase):
    def test_cutaway_template_provides_real_and_example_modes(self):
        html = (CORE / "interfaces/internal/storage/_viewer_3d.html").read_text()
        for expected in (
            'id="storage-3d-real"',
            'id="storage-3d-example"',
            'id="storage-3d-example-notice"',
            'id="storage-3d-canvas"',
            'id="storage-3d-objects"',
        ):
            self.assertIn(expected, html)

    def test_cutaway_uses_authorized_browser_projection_and_local_three(self):
        javascript = (CORE / "static/internal/storage/storage_viewer_3d.js").read_text()
        self.assertIn('$("storage-explorer-data")', javascript)
        self.assertIn("b3-storage-location-selected", javascript)
        self.assertIn("b3-storage-select-request", javascript)
        self.assertIn("../../vendor/three/0.182.0/three.module.js", javascript)
        self.assertIn('mode === "live"', javascript)
        self.assertIn("EXAMPLE", (CORE / "interfaces/internal/storage/_viewer_3d.html").read_text())
        self.assertNotIn("fetch(", javascript)

    def test_storage_workspace_loads_cutaway_above_original_tables(self):
        index = (CORE / "interfaces/internal/storage/index.html").read_text()
        self.assertIn('internal/storage/_viewer_3d.html', index)
        self.assertNotIn(
            'internal/storage/_explorer_v2.html',
            index,
        )

        viewer = (
            CORE / "interfaces/internal/storage/_viewer_3d.html"
        ).read_text()

        self.assertIn(
            'internal/storage/_explorer_v2.html',
            viewer,
        )
        self.assertIn("storage_viewer_3d.js", index)
