"""Static and URL contract tests for selected-Sample storage."""
from pathlib import Path
from django.test import SimpleTestCase
from django.template.loader import get_template
from django.urls import reverse, resolve


class SelectedSampleStorageContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[2]
        cls.list_html = (
            root / "core/interfaces/internal/samples/list.html"
        ).read_text(encoding="utf-8")

    def test_route(self):
        url = reverse("sample_bulk_storage")
        self.assertIn("samples/bulk-storage", url)
        self.assertEqual(resolve(url).url_name, "sample_bulk_storage")

    def test_templates_compile(self):
        self.assertIsNotNone(get_template("internal/samples/list.html"))
        self.assertIsNotNone(get_template("internal/samples/bulk_storage_v8148.html"))

    def test_selected_button_and_form(self):
        self.assertIn('id="moveSelectedSamplesButton"', self.list_html)
        self.assertIn('id="bulkStorageStartForm"', self.list_html)
        self.assertIn('data-b3-can-storage', self.list_html)
        self.assertIn('sample|can_select_for_storage:request.user', self.list_html)

    def test_sharing_retained(self):
        self.assertIn('id="shareSelectedSamplesButton"', self.list_html)
        self.assertIn('id="shareSelectedSamplesModal"', self.list_html)
        self.assertIn('sample_bulk_share', self.list_html)
