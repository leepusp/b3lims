from pathlib import Path

from django.test import SimpleTestCase

CORE = Path(__file__).resolve().parents[1]
TEMPLATE = (CORE / "interfaces/internal/storage/index_v814.html").read_text()
SCRIPT = (CORE / "static/internal/storage/storage_v814.js").read_text()


class StorageBoardContractTests(SimpleTestCase):
    def test_board_lives_in_contents_and_is_wired(self):
        contents = TEMPLATE.index('id="b3s-contents"')
        board = TEMPLATE.index('id="b3s-board"')
        self.assertGreater(board, contents)
        self.assertIn('id="b3s-board-canvas"', TEMPLATE)
        self.assertIn('id="b3s-board-detail"', TEMPLATE)
        self.assertIn("renderBoard();", SCRIPT)
        self.assertIn("wireBoard();", SCRIPT)

    def test_old_layout_tab_and_position_map_are_gone(self):
        self.assertNotIn('data-b3s-tab="layout"', TEMPLATE)
        self.assertNotIn("b3s-layout-levels", TEMPLATE)
        self.assertNotIn("b3s-layout-filled", TEMPLATE)
        self.assertNotIn("b3s-position-map", TEMPLATE)
        self.assertNotIn("renderPositionMap", SCRIPT)
        self.assertNotIn("Levels shown", TEMPLATE)

    def test_board_uses_shared_rules_and_preview_flow(self):
        self.assertIn("window.B3StorageV814.gridSlot", SCRIPT)
        self.assertIn('["preview_sample", "1"]', SCRIPT)
        self.assertIn("pickSampleMove(node", SCRIPT)

    def test_manage_and_historical_blocks_are_restructured(self):
        self.assertIn("b3s-manage-grid", TEMPLATE)
        self.assertIn('class="b3s-historical-block"', TEMPLATE)
