"""Compatibility tests for private ELN document formats."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from core.services.eln_private_drafts import (
    DraftValidationError,
    PrivateDraftRepository,
    logical_revision_path,
)
from core.views.internal.lab_tools.eln_private_web import (
    _values,
)


class MemoryStorage:
    def __init__(self):
        self.files = {}

    def _save(self, name, content):
        if name in self.files:
            raise FileExistsError(name)

        self.files[name] = content.read()
        return name

    def _open(self, name, mode="rb"):
        if name not in self.files:
            raise FileNotFoundError(name)

        return io.BytesIO(self.files[name])

    def listdir(self, name):
        prefix = name.rstrip("/") + "/"

        relative = [
            key[len(prefix):]
            for key in self.files
            if key.startswith(prefix)
        ]

        if not relative:
            raise FileNotFoundError(name)

        directories = set()
        files = set()

        for item in relative:
            if "/" in item:
                directories.add(item.split("/", 1)[0])
            else:
                files.add(item)

        return sorted(directories), sorted(files)


class ElnDocumentFormatTests(SimpleTestCase):

    def setUp(self):
        self.user = SimpleNamespace(
            username="ccalomeno",
            is_authenticated=True,
            is_active=True,
            get_username=lambda: "ccalomeno",
        )
        self.storage = MemoryStorage()
        self.repo = PrivateDraftRepository(
            storage=self.storage
        )

    def test_new_plain_text_is_explicit(self):
        entry = self.repo.create(
            self.user,
            "T2SS",
            title="Legacy text",
            content="Plain notes",
        )

        self.assertEqual(
            entry["content_format"],
            "plain_text",
        )

        self.assertEqual(
            self.repo.latest(
                self.user, "T2SS", entry["entry_id"]
            )["content_format"],
            "plain_text",
        )

    def test_rich_html_is_sanitized_and_persisted(self):
        entry = self.repo.create(
            self.user,
            "T2SS",
            title="Scientific document",
            content_format="rich_html_v1",
            content=(
                "<h2>Results</h2>"
                "<table><tr><td>A1</td></tr></table>"
                '<p onclick="bad()">Observation</p>'
            ),
        )

        self.assertEqual(
            entry["content_format"],
            "rich_html_v1",
        )

        self.assertIn(
            "<table>", entry["content"]
        )

        self.assertNotIn(
            "onclick", entry["content"]
        )

        saved = self.repo.read_revision(
            self.user, "T2SS", entry["entry_id"], 1
        )

        self.assertEqual(
            saved["content_format"],
            "rich_html_v1",
        )

        self.assertEqual(
            saved["content"],
            entry["content"],
        )

    def test_revision_inherits_rich_format(self):
        first = self.repo.create(
            self.user,
            "T2SS",
            title="Experiment",
            content="<p>First</p>",
            content_format="rich_html_v1",
        )

        second = self.repo.revise(
            self.user,
            "T2SS",
            first["entry_id"],
            expected_revision=1,
            title="Experiment",
            content="<p>Second</p>",
        )

        self.assertEqual(
            second["content_format"],
            "rich_html_v1",
        )

        self.assertEqual(second["revision"], 2)

        preserved = self.repo.read_revision(
            self.user,
            "T2SS",
            first["entry_id"],
            1,
        )

        self.assertEqual(
            preserved["content"],
            "<p>First</p>",
        )

    def test_historical_json_without_format(self):
        entry = self.repo.create(
            self.user,
            "T2SS",
            title="Historical",
            content="Old text",
        )

        name = logical_revision_path(
            "ccalomeno",
            "T2SS",
            entry["entry_id"],
            1,
        )

        old_document = json.loads(
            self.storage.files[name]
        )
        old_document.pop("content_format")

        self.storage.files[name] = json.dumps(
            old_document
        ).encode("utf-8")

        loaded = self.repo.read_revision(
            self.user,
            "T2SS",
            entry["entry_id"],
            1,
        )

        self.assertEqual(
            loaded["content_format"],
            "plain_text",
        )

        # Reading must not rewrite the historical file.
        self.assertNotIn(
            "content_format",
            json.loads(self.storage.files[name]),
        )

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(DraftValidationError):
            self.repo.create(
                self.user,
                "T2SS",
                title="Invalid",
                content_format="untrusted_html",
            )

    def test_web_rich_content_format(self):
        request = RequestFactory().post(
            "/",
            {
                "project": "T2SS",
                "title": "Experiment",
                "content_format": "rich_html_v1",
                "content": (
                    '<p onmouseover="bad()">Hello</p>'
                ),
            },
        )

        values = _values(request)

        self.assertEqual(
            values["content_format"],
            "rich_html_v1",
        )

        self.assertEqual(
            values["content"],
            "<p>Hello</p>",
        )

    def test_web_rejects_unknown_format(self):
        request = RequestFactory().post(
            "/",
            {
                "project": "T2SS",
                "title": "Experiment",
                "content_format": "unknown",
            },
        )

        with self.assertRaises(DraftValidationError):
            _values(request)

    def test_editor_has_format_field(self):
        template = Path(
            "core/interfaces/internal/lab_tools/"
            "eln_experimental/private_editor.html"
        )

        html = template.read_text(encoding="utf-8")

        self.assertEqual(
            html.count('name="content_format"'),
            1,
        )

        self.assertIn(
            "values.content_format", html
        )
