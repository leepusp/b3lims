"""The canonical Notebook must never store or render active HTML."""

import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import NotebookEntry
from core.models.samples.sample import Sample
from core.services.notebook_html import sanitize_notebook_html


PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class NotebookHtmlPolicyTests(SimpleTestCase):
    def assertRemoved(self, html, *fragments):
        clean = sanitize_notebook_html(html)
        for fragment in fragments:
            self.assertNotIn(fragment, clean.lower())
        return clean

    def test_scripts_and_event_handlers_are_removed(self):
        self.assertRemoved(
            '<p>ok</p><script>alert(1)</script><img src="x" onerror="alert(2)">'
            '<div onclick="alert(3)" onmouseover="x()">t</div>'
            "<iframe src=\"https://evil\"></iframe><svg onload=alert(4)></svg>",
            "<script", "onerror", "onclick", "onmouseover", "<iframe", "<svg", "onload",
        )

    def test_dangerous_urls_are_removed(self):
        clean = self.assertRemoved(
            '<a href="javascript:alert(1)">a</a>'
            '<a href="data:text/html;base64,PHNjcmlwdD4=">b</a>'
            '<img src="data:image/svg+xml;base64,PHN2Zz4=">'
            '<img src="javascript:alert(1)">',
            "javascript:", "data:text", "svg+xml",
        )
        self.assertIn(">a</a>", clean)

    def test_dangerous_css_is_removed(self):
        clean = self.assertRemoved(
            '<span style="color: red; background: url(https://evil/x.png); '
            'width: expression(alert(1)); position: fixed; '
            'behavior: url(x.htc)">t</span>',
            "url(", "expression", "position", "behavior",
        )
        self.assertIn("color: red", clean)

    def test_quill_formats_are_kept(self):
        html = (
            '<h2>Results</h2><p class="ql-align-center"><strong>bold</strong> '
            '<em>it</em> <u>u</u> <s>s</s></p>'
            '<p><span style="color: rgb(230, 0, 0); background-color: rgb(255, 255, 0);">c</span></p>'
            '<ol><li class="ql-indent-1">one</li></ol>'
            '<p><a href="https://example.org" target="_blank" rel="noopener noreferrer">link</a></p>'
            f'<p><img src="{PNG}"></p>'
        )
        clean = sanitize_notebook_html(html)
        for fragment in (
            '<h2>Results</h2>',
            'class="ql-align-center"',
            'color: rgb(230, 0, 0)',
            'background-color: rgb(255, 255, 0)',
            'class="ql-indent-1"',
            'href="https://example.org"',
            'target="_blank"',
            PNG,
        ):
            self.assertIn(fragment, clean)

    def test_notebook_blocks_are_kept(self):
        html = (
            '<table class="notebook-main-table" data-notebook-widget="table" tabindex="0">'
            '<tbody><tr><th contenteditable="true">Column 1</th></tr>'
            '<tr><td contenteditable="true">&nbsp;</td></tr></tbody></table>'
            '<div class="notebook-molecular-reference-card" data-notebook-widget="molecular-reference" '
            'contenteditable="false" style="border:1px solid #dee2e6;border-radius:6px;'
            'padding:10px 12px;display:flex;justify-content:space-between;">'
            '<a href="/b3lims/internal/molecular/5/" contenteditable="false">Open</a></div>'
        )
        clean = sanitize_notebook_html(html)
        for fragment in (
            'data-notebook-widget="table"',
            'tabindex="0"',
            '<th contenteditable="true">',
            'data-notebook-widget="molecular-reference"',
            'contenteditable="false"',
            "border: 1px solid #dee2e6",
            "justify-content: space-between",
            'href="/b3lims/internal/molecular/5/"',
        ):
            self.assertIn(fragment, clean)

    def test_empty_content(self):
        self.assertEqual(sanitize_notebook_html(None), "")
        self.assertEqual(sanitize_notebook_html(""), "")


@override_settings(FORCE_SCRIPT_NAME=None)
class NotebookHtmlEndpointTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="notebook-html-owner",
            password="test-password",
        )
        self.client.force_login(self.owner)
        self.entry = NotebookEntry.objects.create(
            title="Security entry",
            author=self.owner,
            entry_type="experiment",
            visibility="private",
        )

    def test_save_api_stores_sanitized_content(self):
        response = self.client.post(
            reverse("notebook_entry_update_api", args=[self.entry.id]),
            data=json.dumps(
                {"content": '<p>keep</p><img src="x" onerror="alert(1)"><script>x()</script>'}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertIn("<p>keep</p>", self.entry.content)
        self.assertNotIn("onerror", self.entry.content)
        self.assertNotIn("<script", self.entry.content)

    def test_existing_unsafe_content_is_sanitized_when_rendered(self):
        NotebookEntry.objects.filter(pk=self.entry.pk).update(
            content='<p>legacy</p><img src="x" onerror="alert(\'stored\')">'
        )

        response = self.client.get(reverse("notebook_entry", args=[self.entry.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("<p>legacy</p>", response.context["content_html"])
        self.assertNotIn("onerror", response.context["content_html"])
        self.assertNotIn("alert('stored')", response.content.decode())

    def test_create_from_sample_escapes_sample_fields(self):
        sample = Sample.objects.create(
            sample_id="NB-XSS-001",
            sample_type='<img src=x onerror="alert(1)">',
            organism_name="<script>alert(2)</script>",
            owner=self.owner,
        )

        response = self.client.post(
            reverse("notebook_create_from_sample", args=[sample.id])
        )

        self.assertEqual(response.status_code, 302)
        entry = NotebookEntry.objects.exclude(pk=self.entry.pk).get()
        self.assertNotIn("<img", entry.content)
        self.assertNotIn("<script", entry.content)
        self.assertIn("&lt;script&gt;", entry.content)
