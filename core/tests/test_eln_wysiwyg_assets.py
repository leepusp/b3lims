"""WYSIWYG asset and integration contracts."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from core.views.internal.lab_tools.eln_private_web import (
    _editor,
)


ROOT = Path(__file__).resolve().parents[2]

TEMPLATE = ROOT / (
    "core/interfaces/internal/lab_tools/"
    "eln_experimental/private_editor.html"
)

JS = ROOT / (
    "core/static/internal/lab_tools/"
    "eln_scientific_editor_v1.js"
)

VENDOR = ROOT / (
    "core/static/vendor/suneditor/3.4.1"
)


class ElnWysiwygAssetTests(SimpleTestCase):

    def test_local_editor_assets_exist(self):
        for name in (
            "suneditor.min.js",
            "suneditor.min.css",
            "LICENSE",
        ):
            self.assertTrue(
                (VENDOR / name).is_file(),
                name,
            )

    def test_main_text_uses_local_editor(self):
        html = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn(
            "vendor/suneditor/3.4.1/suneditor.min.js",
            html,
        )

        self.assertIn(
            "eln_scientific_editor_v1.js",
            html,
        )

        self.assertIn(
            'id="eln-content"',
            html,
        )

        self.assertIn(
            'name="content_format"',
            html,
        )

    def test_no_external_editor_delivery(self):
        html = TEMPLATE.read_text(encoding="utf-8")

        self.assertNotIn(
            "cdn.jsdelivr.net",
            html,
        )

        self.assertNotIn(
            "cdn.tiny.cloud",
            html,
        )

    def test_rich_submission_synchronizes_html(self):
        js = JS.read_text(encoding="utf-8")

        self.assertIn(
            "editor.$.html.get()",
            js,
        )

        self.assertIn(
            'format.value = "rich_html_v1"',
            js,
        )

        self.assertIn(
            "plainTextToHtml",
            js,
        )

    def test_no_direct_upload_or_image_tool(self):
        js = JS.read_text(encoding="utf-8")

        self.assertNotIn(
            "uploadUrl",
            js,
        )

        self.assertNotIn(
            '["image"',
            js,
        )
