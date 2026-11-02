"""Canonical B3 ELN navigation regression."""

from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]

BASE = ROOT / "interfaces/internal/common/base.html"

NOTEBOOK = (
    ROOT / "interfaces/internal/lab_tools/notebook.html"
)


class CanonicalElnNavigationTests(SimpleTestCase):

    def test_demo_removed_from_sidebar(self):
        source = BASE.read_text(encoding="utf-8")

        self.assertNotIn(
            "{% url 'eln_experimental_index' %}",
            source,
        )

        self.assertIn(
            "{% url 'notebook_index' %}",
            source,
        )

    def test_both_template_menus_preserved(self):
        source = NOTEBOOK.read_text(encoding="utf-8")

        self.assertEqual(
            source.count(
                "_notebook_template_menu.html"
            ),
            2,
        )

    def test_private_drafts_in_both_states(self):
        source = NOTEBOOK.read_text(encoding="utf-8")

        self.assertEqual(
            source.count(
                "{% url 'eln_private_drafts' %}"
            ),
            2,
        )

        self.assertEqual(
            source.count(
                "{% if show_eln_experimental %}"
            ),
            2,
        )

    def test_original_scientific_tools_preserved(self):
        source = NOTEBOOK.read_text(encoding="utf-8")

        for token in (
            'id="editor-container"',
            'id="notebook-block-workspace"',
            "new Quill(",
            "insertProtocolStep",
            "saveEntry()",
            "createBlock(",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
