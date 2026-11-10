"""Starter Jupyter notebooks, sharing them, and signatures/deviations of ELN entries."""

import contextlib
import io
import json
import os

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import ResearchGroup
from core.models.lab_tools.notebook import JupyterNotebook, NotebookBlock, NotebookEntry
from core.permissions.notebook import can_delete_notebook_entry, can_edit_notebook_entry
from core.services import jupyter_sharing as sharing
from core.services import jupyter_templates as templates
from core.services import notebook_trace as trace

User = get_user_model()


class StarterNotebookTests(TestCase):
    def test_every_template_runs_on_its_demo_data_and_honours_text_parameters(self):
        os.environ.setdefault("MPLBACKEND", "Agg")

        for key in templates.TEMPLATES:
            with self.subTest(key):
                document = templates.build(key, "ana")
                namespace = {"display": lambda value: None, "min_quality": "25", "window": "40", "min_identity": "95"}

                with contextlib.redirect_stdout(io.StringIO()):
                    for cell in document["cells"]:
                        if cell["cell_type"] == "code":
                            exec(compile(cell["source"], key, "exec"), namespace)

    def test_documents_are_valid_nbformat_with_no_stored_outputs(self):
        for key in templates.TEMPLATES:
            document = templates.build(key, "ana")

            self.assertEqual(document["nbformat"], 4)
            self.assertEqual(document["metadata"]["biobank"]["template"], key)
            self.assertTrue(all(c["outputs"] == [] for c in document["cells"] if c["cell_type"] == "code"))
            self.assertTrue(all(isinstance(c["source"], str) for c in document["cells"]))

    def test_template_parameters_are_declared_in_the_first_code_cell(self):
        for key, template in templates.TEMPLATES.items():
            first = next(c for c in template["cells"] if c["cell_type"] == "code")["source"]

            for name in template["parameters"]:
                self.assertIn(f"param('{name}'", first, f"{key}: {name}")

    def test_creating_from_the_index_makes_an_owned_notebook(self):
        ana = User.objects.create_user("ana", password="x")
        self.client.force_login(ana)

        response = self.client.post(reverse("jupyter_from_template"), {"template": "pca_table"})
        notebook = JupyterNotebook.objects.get(owner=ana)

        self.assertRedirects(response, reverse("jupyter_workspace", args=[notebook.pk]), fetch_redirect_response=False)
        self.assertEqual(notebook.title, "PCA of a table")
        self.assertEqual(notebook.visibility, "private")

        self.client.post(reverse("jupyter_from_template"), {"template": "nope"})

        self.assertEqual(JupyterNotebook.objects.count(), 1)

    def test_index_lists_the_templates(self):
        ana = User.objects.create_user("ana", password="x")
        self.client.force_login(ana)

        self.assertContains(self.client.get(reverse("jupyter_index")), "Verify a plasmid against its reference")


class JupyterSharingTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana", password="x")
        self.bia = User.objects.create_user("bia", password="x")
        self.cris = User.objects.create_user("cris", password="x")
        self.group = ResearchGroup.objects.create(name="Phage lab", coordinator=self.cris)
        self.nb = templates.create_notebook(self.ana, "blast_hits")

    def readable(self, user):
        return sharing.readable_notebooks_for_user(user).filter(pk=self.nb.pk).exists()

    def api(self, payload, user=None, notebook=None):
        self.client.force_login(user or self.ana)

        return self.client.post(
            reverse("jupyter_sharing_api", args=[(notebook or self.nb).pk]), json.dumps(payload), content_type="application/json"
        )

    def test_private_by_default(self):
        self.assertTrue(self.readable(self.ana))
        self.assertFalse(self.readable(self.bia))
        self.assertEqual(self.client.get(reverse("jupyter_shared", args=[self.nb.pk])).status_code, 302)  # not logged in

        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(reverse("jupyter_shared", args=[self.nb.pk])).status_code, 404)

    def test_people_and_group_grants_open_reading_only_when_shared(self):
        self.assertEqual(self.api({"action": "add", "kind": "user", "principal_id": self.bia.pk}).json()["visibility"], "shared")
        self.api({"action": "add", "kind": "group", "principal_id": self.group.pk})

        self.assertTrue(self.readable(self.bia))
        self.assertTrue(self.readable(self.cris))  # coordinator of the group

        self.api({"action": "set_visibility", "visibility": "private"})

        self.assertFalse(self.readable(self.bia))
        self.assertFalse(self.readable(self.cris))

    def test_whole_lab_visibility_and_revoking(self):
        self.api({"action": "set_visibility", "visibility": "lab"})

        self.assertTrue(self.readable(self.bia))

        self.api({"action": "set_visibility", "visibility": "shared"})
        grants = self.api({"action": "add", "kind": "user", "principal_id": self.bia.pk}).json()["grants"]
        self.api({"action": "remove", "grant_id": grants[0]["id"]})

        self.assertFalse(self.readable(self.bia))

    def test_only_the_owner_changes_sharing(self):
        self.api({"action": "set_visibility", "visibility": "lab"})

        for payload in ({"action": "set_visibility", "visibility": "private"}, {"action": "add", "kind": "user", "principal_id": self.cris.pk}, {"action": "get"}):
            self.assertEqual(self.api(payload, user=self.bia).status_code, 403)

        self.nb.refresh_from_db()

        self.assertEqual(self.nb.visibility, "lab")

    def test_sharing_does_not_open_the_workspace_or_execution(self):
        from core.services.jupyter_server import visible_notebooks_for_user

        self.api({"action": "set_visibility", "visibility": "lab"})

        self.assertFalse(visible_notebooks_for_user(self.bia).filter(pk=self.nb.pk).exists())

        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(reverse("jupyter_workspace", args=[self.nb.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("jupyter_download", args=[self.nb.pk])).status_code, 404)

    def test_reader_sees_the_cells_as_escaped_text_and_can_copy(self):
        self.nb.notebook_json["cells"].append({"cell_type": "markdown", "metadata": {}, "source": "<script>alert(1)</script>"})
        self.nb.notebook_json["cells"][1]["outputs"] = [{"output_type": "stream", "text": "secret output"}]
        self.nb.save()
        self.api({"action": "set_visibility", "visibility": "lab"})
        self.client.force_login(self.bia)

        page = self.client.get(reverse("jupyter_shared", args=[self.nb.pk]))

        self.assertContains(page, "Use a copy")
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(page, "secret output")

        response = self.client.post(reverse("jupyter_copy", args=[self.nb.pk]))
        mine = JupyterNotebook.objects.get(owner=self.bia)

        self.assertRedirects(response, reverse("jupyter_workspace", args=[mine.pk]), fetch_redirect_response=False)
        self.assertEqual(mine.visibility, "private")
        self.assertEqual(mine.notebook_json["metadata"]["biobank"]["owner"], "bia")
        self.assertEqual(mine.notebook_json["metadata"]["biobank"]["copied_from"], self.nb.pk)
        self.assertTrue(all(c.get("outputs") == [] for c in mine.notebook_json["cells"] if c["cell_type"] == "code"))
        self.assertEqual(self.nb.owner, self.ana)

    def test_unshared_notebooks_cannot_be_copied(self):
        self.client.force_login(self.bia)

        self.assertEqual(self.client.post(reverse("jupyter_copy", args=[self.nb.pk])).status_code, 404)
        self.assertFalse(JupyterNotebook.objects.filter(owner=self.bia).exists())

    def test_index_shows_what_was_shared_with_you(self):
        self.api({"action": "set_visibility", "visibility": "lab"})
        self.client.force_login(self.bia)

        page = self.client.get(reverse("jupyter_index"))

        self.assertContains(page, "Shared with you")
        self.assertContains(page, reverse("jupyter_shared", args=[self.nb.pk]))

    def test_search_finds_people_and_groups_but_not_the_owner(self):
        found = self.api({"action": "search", "q": "ph"}).json()["results"]
        people = self.api({"action": "search", "q": "an"}).json()["results"]

        self.assertEqual([r["name"] for r in found], ["Phage lab"])
        self.assertNotIn("ana", [r["detail"] for r in people])


@override_settings(FORCE_SCRIPT_NAME=None)
class NotebookTraceTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana", password="x")
        self.bia = User.objects.create_user("bia", password="x")
        self.eve = User.objects.create_user("eve", password="x")
        self.entry = NotebookEntry.objects.create(title="Growth curve", author=self.ana, visibility="lab", content="<p>OD 0.6</p>")
        self.client.force_login(self.ana)

    def api(self, payload, user=None, entry=None):
        self.client.force_login(user or self.ana)

        return self.client.post(reverse("notebook_trace_api", args=[(entry or self.entry).pk]), json.dumps(payload), content_type="application/json")

    def sign(self):
        r = self.api({"action": "sign", "meaning": "author", "comment": "done"})
        self.entry.refresh_from_db()

        return r

    def test_signing_locks_the_entry_for_everyone_even_the_author(self):
        self.assertTrue(can_edit_notebook_entry(self.ana, self.entry))
        self.assertEqual(self.sign().status_code, 200)
        admin = User.objects.create_superuser("root", "r@x.y", "x")

        self.assertIsNotNone(self.entry.signed_at)
        self.assertFalse(can_edit_notebook_entry(self.ana, self.entry))
        self.assertFalse(can_edit_notebook_entry(admin, self.entry))
        self.assertFalse(can_delete_notebook_entry(self.ana, self.entry))

    def test_locked_entry_refuses_content_changes_through_the_update_api(self):
        self.sign()
        response = self.client.post(
            reverse("notebook_entry_update_api", args=[self.entry.pk]), json.dumps({"title": "Sneaky", "content": "<p>changed</p>"}), content_type="application/json"
        )
        self.entry.refresh_from_db()

        self.assertIn(response.status_code, (400, 403))
        self.assertEqual(self.entry.title, "Growth curve")

    def test_only_the_author_signs_as_author_and_only_once(self):
        self.assertEqual(self.api({"action": "sign", "meaning": "author"}, user=self.bia).status_code, 403)
        self.sign()

        self.assertEqual(self.api({"action": "sign", "meaning": "author"}).status_code, 400)

    def test_witness_needs_a_signed_entry_and_cannot_be_the_author(self):
        self.assertEqual(self.api({"action": "sign", "meaning": "witness"}, user=self.bia).status_code, 400)
        self.sign()

        self.assertEqual(self.api({"action": "sign", "meaning": "witness"}).status_code, 403)
        self.assertEqual(self.api({"action": "sign", "meaning": "witness", "comment": "seen"}, user=self.bia).status_code, 200)
        self.assertEqual(self.api({"action": "sign", "meaning": "witness"}, user=self.bia).status_code, 400)
        self.assertEqual(self.api({"action": "sign", "meaning": "reviewer"}, user=self.eve).status_code, 200)

    def test_nobody_signs_what_they_cannot_open(self):
        private = NotebookEntry.objects.create(title="Mine", author=self.ana, visibility="private")

        self.assertEqual(self.api({"action": "state"}, user=self.bia, entry=private).status_code, 404)

    def test_signature_records_a_digest_and_detects_later_changes(self):
        self.sign()

        self.assertTrue(self.api({"action": "state"}).json()["trace"]["intact"])

        NotebookEntry.objects.filter(pk=self.entry.pk).update(content="<p>OD 0.9</p>")  # a change behind the application's back
        state = self.api({"action": "state"}).json()["trace"]

        self.assertFalse(state["intact"])
        self.assertFalse(state["signatures"][0]["intact"])

    def test_digest_covers_blocks_steps_and_tables(self):
        before = trace.content_digest(self.entry)

        NotebookBlock.objects.create(entry=self.entry, block_type="protocol", title="P", content_data={"text": "x"})
        after_block = trace.content_digest(self.entry)
        self.entry.steps.create(body="Add buffer", position=1)
        after_step = trace.content_digest(self.entry)

        self.assertEqual(len({before, after_block, after_step}), 3)
        self.assertEqual(after_step, trace.content_digest(self.entry))

    def test_amending_needs_a_reason_unlocks_voids_signatures_and_keeps_history(self):
        self.sign()
        self.api({"action": "sign", "meaning": "witness"}, user=self.bia)

        self.assertEqual(self.api({"action": "amend", "reason": "short"}, user=self.ana).status_code, 400)
        self.assertEqual(self.api({"action": "amend", "reason": "Wrong OD reading, fixing it"}, user=self.bia).status_code, 403)

        response = self.api({"action": "amend", "reason": "Wrong OD reading, fixing it"}, user=self.ana)
        self.entry.refresh_from_db()
        state = response.json()["trace"]

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.entry.signed_at)
        self.assertTrue(can_edit_notebook_entry(self.ana, self.entry))
        self.assertFalse(state["locked"])
        self.assertEqual([s["superseded_reason"] for s in state["signatures"]], ["Wrong OD reading, fixing it"] * 2)
        self.assertEqual(self.entry.revisions.count(), 1)

        self.sign()

        self.assertEqual(self.entry.signatures.filter(superseded_at__isnull=True).count(), 1)

    def test_deviations_can_be_recorded_after_signing_and_resolved(self):
        self.sign()
        self.assertEqual(self.api({"action": "add_deviation", "description": "Incubator at 35 C", "impact": "major", "step": "Step 2"}, user=self.bia).status_code, 403)

        r = self.api({"action": "add_deviation", "description": "Incubator at 35 C", "impact": "major", "step": "Step 2"})
        row = r.json()["trace"]["deviations"][0]

        self.assertEqual((row["impact"], row["step"], row["resolved"]), ("major", "Step 2", False))
        self.assertEqual(self.api({"action": "add_deviation", "description": " "}).status_code, 400)
        self.assertEqual(self.api({"action": "add_deviation", "description": "x", "impact": "huge"}).status_code, 400)
        self.assertEqual(self.api({"action": "resolve_deviation", "id": row["id"], "resolution": ""}).status_code, 400)

        done = self.api({"action": "resolve_deviation", "id": row["id"], "resolution": "Repeated at 37 C"}).json()["trace"]["deviations"][0]

        self.assertTrue(done["resolved"])
        self.assertEqual(done["resolution"], "Repeated at 37 C")

    def test_entry_page_has_the_record_tab_and_url(self):
        page = self.client.get(reverse("notebook_entry", args=[self.entry.pk]))

        self.assertContains(page, 'data-pane="record"')
        self.assertContains(page, reverse("notebook_trace_api", args=[self.entry.pk]))

    def test_signed_entry_cannot_be_trashed_but_comments_still_work(self):
        self.sign()

        r = self.client.post(reverse("notebook_comments_api", args=[self.entry.pk]), json.dumps({"action": "add", "body": "Looks right"}), content_type="application/json")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(can_delete_notebook_entry(self.ana, self.entry))
