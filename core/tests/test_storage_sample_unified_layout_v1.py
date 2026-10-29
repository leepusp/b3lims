"""Regression tests for the unified physical storage card."""

from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase


class SampleUnifiedStorageLayoutTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        root = Path(__file__).resolve().parents[2]

        cls.html = (
            root
            / "core/interfaces/internal/samples/samples.html"
        ).read_text(encoding="utf-8")

    def test_template_compiles(self):
        self.assertIsNotNone(
            get_template("internal/samples/samples.html")
        )

    def test_unified_storage_card(self):
        self.assertEqual(
            self.html.count(
                'id="b3s-unified-storage-card"'
            ),
            1,
        )

        self.assertIn("Physical storage", self.html)

    def test_original_columns_preserved(self):
        for marker in (
            'class="row g-3 align-items-start"',
            'class="col-lg-5"',
            'class="col-lg-7"',
        ):
            self.assertIn(marker, self.html)

    def test_workspace_precedes_path(self):
        workspace = (
            '{% include '
            '"internal/samples/_storage_child_v8146.html" %}'
        )

        self.assertLess(
            self.html.index(workspace),
            self.html.index('id="dynamicStorageContainer"'),
        )

    def test_storage_fields_preserved(self):
        for field in (
            "storage_location_hidden",
            "storage_mode_v8",
            "storage_anchor_id_v8",
            "storageInputVisual",
            "storagePositionPanelV8",
            "storagePositionRowsV8",
        ):
            self.assertEqual(
                self.html.count(f'id="{field}"'),
                1,
            )

    def test_responsive_alignment(self):
        self.assertIn(
            "display: grid",
            self.html,
        )

        self.assertIn(
            "align-items: stretch",
            self.html,
        )

        self.assertIn(
            "@media (max-width: 991.98px)",
            self.html,
        )

    def test_no_duplicate_workspace_attribute_selector(self):
        self.assertNotIn(
            "[data-b3-storage-child-v8146]",
            self.html,
        )

        self.assertIn(
            "> .row > .col-lg-5 > section",
            self.html,
        )
