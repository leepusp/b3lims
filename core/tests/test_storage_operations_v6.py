from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class StorageOperationsV6Tests(SimpleTestCase):
    def test_workspace_uses_existing_server_forms(self):
        index = (
            ROOT / "interfaces/internal/storage/index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id="b3-ops-source"', index)
        self.assertIn('storage_operations_v6.js', index)
        self.assertIn('value="confirm_container_move"', index)
        self.assertIn('value="assign_sample"', index)
        self.assertIn('value="create_location"', index)

    def test_spatial_designer_contains_tool_navigation(self):
        html = (
            ROOT / "interfaces/internal/storage/_viewer_3d.html"
        ).read_text(encoding="utf-8")

        for tool in (
            "explore",
            "locations",
            "samples",
            "transfers",
            "history",
        ):
            self.assertIn(
                f'data-b3-v6-tab="{tool}"',
                html,
            )

        self.assertIn('id="b3-v6-ops-host"', html)
        self.assertIn('id="b3-v5-views"', html)

    def test_operations_move_existing_cards(self):
        js = (
            ROOT / "static/internal/storage/storage_operations_v6.js"
        ).read_text(encoding="utf-8")

        self.assertIn('header.closest(".card")', js)
        self.assertIn('move(card, panes.get(group));', js)
        self.assertIn('source.dataset.integrated = "true"', js)
        self.assertIn('source.querySelector("form")', js)


    def test_failed_integration_restores_original_elements(self):
        js = (
            ROOT / "static/internal/storage/storage_operations_v6.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const relocationJournal = [];", js)
        self.assertIn("function restore()", js)
        self.assertIn("entry.parent.insertBefore", js)
        self.assertIn("restore();", js)
        self.assertIn(
            'move(card, panes.get("more"));',
            js,
        )

    def test_original_inventory_forms_remain_in_template(self):
        index = (
            ROOT / "interfaces/internal/storage/index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("Movement History", index)
        self.assertIn("Storage hierarchy", index)
        self.assertIn("Current Sample occupancy", index)
