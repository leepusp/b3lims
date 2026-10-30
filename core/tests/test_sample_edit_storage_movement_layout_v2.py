"""Keep Edit Sample storage within one outer card."""

from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase


class EditSampleStorageMovementLayoutTests(SimpleTestCase):

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

    def test_storage_components_occur_once(self):
        for marker in (
            'id="b3-edit-unified-storage"',
            'id="dynamicStorageContainer"',
            'id="storage_location_hidden"',
            'id="storage_edit_intent"',
            'id="storageInputVisual"',
            "_storage_child_v8146.html",
            "_storage_move_v8146.html",
            "data-b3-edit-storage-movement",
        ):
            self.assertEqual(
                self.html.count(marker),
                1,
                marker,
            )

    def test_movement_inside_storage_card(self):
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
            block.index('id="dynamicStorageContainer"'),
        )
        self.assertLess(
            block.index('id="dynamicStorageContainer"'),
            block.index("_storage_move_v8146.html"),
        )

        self.assertLess(
            block.index("_storage_move_v8146.html"),
            block.rfind("</section>"),
        )

    def test_governance_controls_preserved(self):
        self.assertIn(
            "{{ form.is_public }}",
            self.html,
        )
        self.assertIn(
            "{{ form.is_embargoed }}",
            self.html,
        )
        self.assertIn(
            "{{ sample.get_status_display }}",
            self.html,
        )
