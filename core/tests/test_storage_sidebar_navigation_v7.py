from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse


ROOT = Path(__file__).resolve().parents[1]


class StorageSidebarNavigationTests(SimpleTestCase):
    def test_storage_not_in_global_sidebar(self):
        html = (
            ROOT / "interfaces/internal/common/base.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            '<a href="{% url \'storage_workspace\' %}"',
            html,
        )

    def test_samples_page_retains_storage_access(self):
        html = (
            ROOT / "interfaces/internal/samples/list.html"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "{% url 'storage_workspace' %}",
            html,
        )

    def test_storage_route_is_preserved(self):
        self.assertTrue(reverse("storage_workspace"))
