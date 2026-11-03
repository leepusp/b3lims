"""B3 ELN 2.0 — document-centred entry page."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Sample
from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_composer import (
    NotebookEntryLink,
    NotebookSpreadsheet,
    NotebookStep,
)
from core.services import notebook_composer as composer


@override_settings(FORCE_SCRIPT_NAME=None)
class EntryPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="entry-owner", password="x")
        cls.other = User.objects.create_user(username="entry-other", password="x")
        cls.entry = NotebookEntry.objects.create(
            title="Plaque assay", author=cls.owner, visibility="lab",
            content="<p>legacy</p><img src=x onerror=alert(1)>",
        )
        cls.private = NotebookEntry.objects.create(title="Private", author=cls.other)
        cls.sample = Sample.objects.create(sample_id="B3-S-1", sample_type="Bacteria", owner=cls.owner)
        cls.hidden_sample = Sample.objects.create(sample_id="B3-S-HIDDEN", sample_type="Bacteria", owner=cls.other)

    def setUp(self):
        self.client.force_login(self.owner)

    def post(self, name, payload, entry=None):
        return self.client.post(
            reverse(name, args=[(entry or self.entry).pk]),
            data=json.dumps(payload), content_type="application/json",
        )

    # --- page -----------------------------------------------------------------

    def test_page_renders_editor_and_sanitized_content(self):
        response = self.client.get(reverse("notebook_entry", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        for fragment in ("tinymce.min.js", "jspreadsheet.js", "notebook_entry_v1.js",
                         'id="bx-state"', 'id="nb-composer"', "Relevant items"):
            self.assertContains(response, fragment)
        self.assertContains(response, "&lt;p&gt;legacy&lt;/p&gt;")  # escaped inside the editor textarea
        self.assertNotContains(response, "onerror=alert(1)")

    def test_other_users_see_read_only_page(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("notebook_entry", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="bx-editor"')
        self.assertContains(response, "Read only")

    def test_private_entry_of_someone_else_is_hidden(self):
        response = self.client.get(reverse("notebook_entry", args=[self.private.pk]))
        self.assertEqual(response.status_code, 404)

    def test_open_latest_and_new_entries_land_on_new_page(self):
        response = self.client.get(reverse("notebook_entry_open_latest"))
        self.assertRedirects(response, reverse("notebook_entry", args=[self.entry.pk]), fetch_redirect_response=False)
        response = self.client.get(reverse("notebook_create") + "?template=experiment")
        created = NotebookEntry.objects.filter(author=self.owner).exclude(pk=self.entry.pk).get()
        self.assertRedirects(response, reverse("notebook_entry", args=[created.pk]), fetch_redirect_response=False)

    # --- updates ----------------------------------------------------------------

    def test_partial_update_sanitizes_and_validates(self):
        response = self.post("notebook_entry_update_api", {
            "title": "Titer v2", "status": "in_progress", "experiment_date": "2026-11-02",
            "content": '<h2 style="text-align: center">Results</h2><script>x()</script>',
        })
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.title, self.entry.status), ("Titer v2", "in_progress"))
        self.assertIn("text-align: center", self.entry.content)
        self.assertNotIn("<script", self.entry.content)

        for payload in ({"status": "bogus"}, {"experiment_date": "02/11/2026"}, {"author": 3}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post("notebook_entry_update_api", payload).status_code, 400)

    def test_only_editors_can_update(self):
        self.client.force_login(self.other)
        self.assertIn(self.post("notebook_entry_update_api", {"title": "x"}).status_code, {403, 404})

    # --- spreadsheets -----------------------------------------------------------

    def test_spreadsheet_lifecycle_keeps_formulas(self):
        response = self.post("notebook_spreadsheets_api", {"action": "add", "title": "Master mix"})
        sheet_id = response.json()["sheet"]["id"]
        data = [["Component", "uL", "n", "Total"], ["Water", "16", "80", "=B2*C2"]]
        self.post("notebook_spreadsheets_api", {"action": "save", "sheet_id": sheet_id, "data": data, "column_widths": [140, 9999]})
        sheet = NotebookSpreadsheet.objects.get(pk=sheet_id)
        self.assertEqual(sheet.data[1][3], "=B2*C2")
        self.assertEqual(sheet.column_widths, [140, 600])

        self.post("notebook_spreadsheets_api", {"action": "rename", "sheet_id": sheet_id, "title": "PCR mix"})
        sheet.refresh_from_db()
        self.assertEqual(sheet.title, "PCR mix")

        too_big = [["x"] * 61]
        self.assertEqual(self.post("notebook_spreadsheets_api", {"action": "save", "sheet_id": sheet_id, "data": too_big}).status_code, 400)

        self.post("notebook_spreadsheets_api", {"action": "delete", "sheet_id": sheet_id})
        self.assertFalse(NotebookSpreadsheet.objects.exists())

    # --- duplicate ----------------------------------------------------------------

    def test_duplicate_copies_structure_into_private_draft(self):
        composer.update_header(self.entry, tags=["bsl2"])
        NotebookStep.objects.create(entry=self.entry, body="Plate", finished=True)
        NotebookSpreadsheet.objects.create(entry=self.entry, title="T", data=[["=1+1"]])
        self.entry.metadata = {"extra_fields": {"Medium": {"type": "text", "value": "TSB"}}}
        self.entry.save()

        self.client.force_login(self.other)
        response = self.post("notebook_duplicate_api", {})
        copy = NotebookEntry.objects.get(pk=response.json()["entry_id"])
        self.assertEqual(copy.author, self.other)
        self.assertEqual((copy.status, copy.visibility), ("draft", "private"))
        self.assertEqual(copy.metadata["extra_fields"]["Medium"]["value"], "TSB")
        self.assertEqual([t.name for t in copy.tags.all()], ["bsl2"])
        self.assertEqual([(s.body, s.finished) for s in copy.steps.all()], [("Plate", False)])
        self.assertEqual(copy.spreadsheets.get().data, [["=1+1"]])
        self.assertTrue(NotebookEntryLink.objects.filter(entry=copy, target=self.entry).exists())

    # --- relevant items -------------------------------------------------------------

    def test_relevant_items_link_only_visible_records(self):
        url = reverse("notebook_relevant_api", args=[self.entry.pk])
        ids = {r["id"] for r in self.client.get(url, {"kind": "samples", "q": "B3-S"}).json()["results"]}
        self.assertIn(self.sample.pk, ids)
        self.assertNotIn(self.hidden_sample.pk, ids)

        response = self.post("notebook_relevant_api", {"action": "link", "kind": "samples", "id": self.sample.pk})
        self.assertEqual(response.status_code, 200)
        samples = response.json()["relevant"]["samples"]
        self.assertEqual([s["id"] for s in samples], [self.sample.pk])

        response = self.post("notebook_relevant_api", {"action": "link", "kind": "samples", "id": self.hidden_sample.pk})
        self.assertEqual(response.status_code, 400)

        response = self.post("notebook_relevant_api", {"action": "unlink", "kind": "samples", "link_id": samples[0]["link_id"]})
        self.assertEqual(response.json()["relevant"]["samples"], [])

    def test_files_api_lists_attachments(self):
        response = self.client.get(reverse("notebook_entry_files_api", args=[self.entry.pk]))
        self.assertEqual(response.json(), {"status": "success", "attachments": []})
