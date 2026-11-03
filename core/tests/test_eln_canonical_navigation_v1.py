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

