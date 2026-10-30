"""Edit Sample: one wide physical storage section, no move panel."""

from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase


class EditSampleStorageLayoutTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[2]
        cls.html = (
            root / "core/interfaces/internal/samples/edit.html"
        ).read_text(encoding="utf-8")

    def test_template_compiles(self):
        self.assertIsNotNone(
            get_template("internal/samples/edit.html")
        )

    def test_storage_fields_exist_once(self):
        for marker in (
            'id="b3-edit-unified-storage"',
            'id="dynamicStorageContainer"',
            'id="storage_location_hidden"',
            'id="storage_edit_intent"',
            'id="storageInputVisual"',
            "_storage_child_v8146.html",
        ):
            with self.subTest(marker=marker):
                self.assertEqual(
                    self.html.count(marker), 1
                )

    def test_physical_storage_spans_both_columns(self):
        self.assertIn(
            '"physical-storage physical-storage"',
            self.html,
        )
        self.assertIn(
            "grid-area: physical-storage;",
            self.html,
        )

    def test_separate_movement_panel_removed(self):
        for marker in (
            "_storage_move_v8146.html",
            "data-b3-edit-storage-movement",
            "sample-physical-movement-v8146",
            "Moving an existing registered Sample location",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.html)

    def test_current_registered_storage_visible(self):
        self.assertIn(
            "data-b3-current-sample-storage>",
            self.html,
        )
        self.assertIn(
            "storage_edit_assignments_v8146",
            self.html,
        )
        self.assertIn(
            "data-b3-current-assignment",
            self.html,
        )

    def test_storage_controls_share_one_card(self):
        start = self.html.index(
            '<section id="b3-edit-unified-storage"'
        )
        end = self.html.index(
            "<!-- Biological subtype metadata",
            start,
        )
        block = self.html[start:end]

        self.assertLess(
            block.index("_storage_child_v8146.html"),
            block.index("data-b3-current-sample-storage>"),
        )
        self.assertLess(
            block.index("data-b3-current-sample-storage>"),
            block.index('id="dynamicStorageContainer"'),
        )

    def test_governance_controls_preserved(self):
        for marker in (
            "{{ form.is_public }}",
            "{{ form.is_embargoed }}",
            "{{ sample.get_status_display }}",
        ):
            self.assertIn(marker, self.html)
