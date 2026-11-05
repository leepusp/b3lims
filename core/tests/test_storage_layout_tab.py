from pathlib import Path

from django.test import SimpleTestCase

CORE = Path(__file__).resolve().parents[1]
TEMPLATE = (CORE / "interfaces/internal/storage/index_v814.html").read_text()
SCRIPT = (CORE / "static/internal/storage/storage_v814.js").read_text()


class StorageLayoutTabContractTests(SimpleTestCase):
    def test_tab_and_panel_exist_and_are_wired(self):
        self.assertIn('data-b3s-tab="layout"', TEMPLATE)
        self.assertIn('id="b3s-layout"', TEMPLATE)
        self.assertIn('id="b3s-layout-canvas"', TEMPLATE)
        self.assertIn('id="b3s-layout-detail"', TEMPLATE)
        self.assertIn('["layout", "b3s-layout"]', SCRIPT)
        self.assertIn("renderLayout();", SCRIPT)
        self.assertIn("wireLayout();", SCRIPT)

    def test_layout_uses_the_shared_occupancy_rule(self):
        self.assertIn("window.B3StorageV814.gridSlot", SCRIPT)
        self.assertIn("summary(node)", SCRIPT)

    def test_manage_and_historical_blocks_are_restructured(self):
        self.assertIn("b3s-manage-grid", TEMPLATE)
        self.assertIn('class="b3s-historical-block"', TEMPLATE)
