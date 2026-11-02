"""ELN scientific HTML safety and editor layout."""

from pathlib import Path

from django.test import RequestFactory, SimpleTestCase

from core.services.eln_private_drafts import DraftValidationError
from core.services.eln_rich_content import sanitize_rich_content
from core.views.internal.lab_tools.eln_private_web import _values


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "interfaces/internal/lab_tools/"
    "eln_experimental/private_editor.html"
)


class ElnRichContentTests(SimpleTestCase):

    def test_headings_and_tables_are_retained(self):
        source = (
            "<h2>Results</h2>"
            "<table><tbody><tr><th>Sample</th>"
            "<td>A1</td></tr></tbody></table>"
        )

        clean = sanitize_rich_content(source)

        self.assertIn("<h2>Results</h2>", clean)
        self.assertIn("<table>", clean)
        self.assertIn("<th>Sample</th>", clean)

    def test_scripts_and_event_handlers_removed(self):
        clean = sanitize_rich_content(
            '<p onclick="alert(1)">Experiment</p>'
            '<script>alert(2)</script>'
            '<img src=x onerror="alert(3)">'
        )

        self.assertNotIn("<script", clean)
        self.assertNotIn("<img", clean)
        self.assertNotIn("onclick", clean)
        self.assertNotIn("onerror", clean)
        self.assertIn("Experiment", clean)

    def test_unsafe_links_are_removed(self):
        clean = sanitize_rich_content(
            '<a href="javascript:alert(1)">Unsafe</a>'
        )

        self.assertNotIn("javascript:", clean)
        self.assertIn("Unsafe", clean)

    def test_https_link_allowed(self):
        clean = sanitize_rich_content(
            '<a href="https://example.org">Reference</a>'
        )

        self.assertIn(
            'href="https://example.org"',
            clean,
        )

    def test_oversized_document_rejected(self):
        with self.assertRaises(DraftValidationError):
            sanitize_rich_content(
                "A" * 512_001
            )

    def test_rich_post_uses_sanitizer(self):
        request = RequestFactory().post(
            "/",
            {
                "project": "T2SS",
                "title": "Experiment",
                "content_format": "rich_html_v1",
                "content": '<p onmouseover="x()">Hello</p>',
            },
        )

        values = _values(request)

        self.assertEqual(
            values["content"],
            "<p>Hello</p>",
        )

    def test_plain_text_remains_unchanged(self):
        request = RequestFactory().post(
            "/",
            {
                "project": "T2SS",
                "title": "Experiment",
                "content": "Legacy text <not html>",
            },
        )

        values = _values(request)

        self.assertEqual(
            values["content"],
            "Legacy text <not html>",
        )

    def test_materials_are_in_sidebar(self):
        html = TEMPLATE.read_text(encoding="utf-8")

        sidebar = html.index(
            '<div class="col-xl-4">'
        )

        self.assertLess(
            sidebar,
            html.index('id="eln-samples"'),
        )

        self.assertLess(
            sidebar,
            html.index('id="eln-chemicals"'),
        )

        self.assertEqual(
            html.count('form="eln-editor-form"'),
            2,
        )

        self.assertEqual(
            html.count('id="eln-editor-form"'),
            1,
        )
