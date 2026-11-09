import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.workflow import Workflow, WorkflowEdge, WorkflowStep
from core.services import notebook_composer as composer


class WorkflowBase(TestCase):
    def setUp(self):
        User = get_user_model()

        self.ana = User.objects.create_user("ana", password="x")
        self.bia = User.objects.create_user("bia", password="x")
        self.cris = User.objects.create_user("cris", password="x")
        self.client.force_login(self.ana)
        self.workflow = Workflow.objects.create(name="Cloning", owner=self.ana)

    def api(self, payload, user=None, workflow=None):
        if user:
            self.client.force_login(user)

        url = reverse("workflow_api", args=[(workflow or self.workflow).pk])

        return self.client.post(url, json.dumps(payload), content_type="application/json")

    def add(self, title="Step", **extra):
        response = self.api({"action": "add_step", "step": {"title": title, **extra}})

        self.assertEqual(response.status_code, 200, response.content)

        return response.json()["step_id"]


class WorkflowAccessTests(WorkflowBase):
    def test_only_owner_members_and_superusers_can_see_and_edit(self):
        self.assertEqual(self.client.get(reverse("workflow_detail", args=[self.workflow.pk])).status_code, 200)

        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(reverse("workflow_detail", args=[self.workflow.pk])).status_code, 404)
        self.assertEqual(self.api({"action": "update", "name": "x"}).status_code, 404)

        self.workflow.members.add(self.bia)

        self.assertEqual(self.client.get(reverse("workflow_detail", args=[self.workflow.pk])).status_code, 200)
        self.assertEqual(self.api({"action": "update", "name": "Renamed"}).status_code, 200)

    def test_members_cannot_delete_or_change_the_member_list(self):
        self.workflow.members.add(self.bia)

        self.assertEqual(self.api({"action": "delete"}, user=self.bia).status_code, 400)

        self.api({"action": "update", "members": [self.cris.pk]}, user=self.bia)

        self.assertEqual(list(self.workflow.members.values_list("pk", flat=True)), [self.bia.pk])

        self.assertEqual(self.api({"action": "update", "members": [self.cris.pk]}, user=self.ana).status_code, 200)
        self.assertEqual(list(self.workflow.members.values_list("pk", flat=True)), [self.cris.pk])

    def test_list_page_shows_only_visible_workflows_and_create_redirects(self):
        Workflow.objects.create(name="Secret", owner=self.bia)

        page = self.client.get(reverse("workflow_list"))

        self.assertContains(page, "Cloning")
        self.assertNotContains(page, "Secret")

        created = self.client.post(reverse("workflow_create"), {"name": "New flow"})

        self.assertEqual(created.status_code, 302)
        self.assertTrue(Workflow.objects.filter(name="New flow", owner=self.ana).exists())

    def test_owner_can_delete(self):
        response = self.api({"action": "delete"})

        self.assertTrue(response.json()["deleted"])
        self.assertFalse(Workflow.objects.filter(pk=self.workflow.pk).exists())


class WorkflowStepTests(WorkflowBase):
    def test_add_update_and_validate_steps(self):
        sid = self.add("Extract DNA", due_date="2026-12-01T09:00")
        step = WorkflowStep.objects.get(pk=sid)

        self.assertEqual(step.title, "Extract DNA")
        self.assertIsNotNone(step.due_date)

        done = self.api({"action": "update_step", "step_id": sid, "step": {"status": "done"}})

        self.assertEqual(done.status_code, 200)

        step.refresh_from_db()

        self.assertEqual(step.status, "done")
        self.assertIsNotNone(step.finished_at)
        self.assertEqual(self.api({"action": "update_step", "step_id": sid, "step": {"status": "nope"}}).status_code, 400)
        self.assertEqual(self.api({"action": "update_step", "step_id": sid, "step": {"title": " "}}).status_code, 400)

        self.api({"action": "update_step", "step_id": sid, "step": {"status": "todo"}})
        step.refresh_from_db()

        self.assertIsNone(step.finished_at)

    def test_links_must_be_visible_to_the_user(self):
        mine = NotebookEntry.objects.create(title="Mine", author=self.ana)
        theirs = NotebookEntry.objects.create(title="Theirs", author=self.bia)
        sid = self.add("A")

        ok = self.api({"action": "update_step", "step_id": sid, "step": {"entry": mine.pk}})
        bad = self.api({"action": "update_step", "step_id": sid, "step": {"entry": theirs.pk}})

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(WorkflowStep.objects.get(pk=sid).entry_id, mine.pk)

    def test_move_steps_saves_positions(self):
        sid = self.add("A")

        self.api({"action": "move_steps", "positions": [{"id": sid, "x": 300, "y": 220}]})

        step = WorkflowStep.objects.get(pk=sid)

        self.assertEqual((step.x, step.y), (300, 220))

    def test_unknown_action_and_bad_json_are_rejected(self):
        self.assertEqual(self.api({"action": "explode"}).status_code, 400)

        response = self.client.post(
            reverse("workflow_api", args=[self.workflow.pk]), "not json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)


class WorkflowEdgeTests(WorkflowBase):
    def test_edges_connect_steps_and_refuse_loops_and_self_links(self):
        a, b, c = self.add("A"), self.add("B"), self.add("C")

        self.assertEqual(self.api({"action": "add_edge", "source": a, "target": b}).status_code, 200)
        self.assertEqual(self.api({"action": "add_edge", "source": b, "target": c}).status_code, 200)
        self.assertEqual(self.api({"action": "add_edge", "source": c, "target": a}).status_code, 400)
        self.assertEqual(self.api({"action": "add_edge", "source": a, "target": a}).status_code, 400)

        self.api({"action": "add_edge", "source": a, "target": b})

        self.assertEqual(WorkflowEdge.objects.filter(workflow=self.workflow).count(), 2)

    def test_edges_cannot_cross_workflows_and_can_be_removed(self):
        other = Workflow.objects.create(name="Other", owner=self.ana)
        a = self.add("A")
        foreign = WorkflowStep.objects.create(workflow=other, title="F")

        self.assertEqual(self.api({"action": "add_edge", "source": a, "target": foreign.pk}).status_code, 400)

        b = self.add("B")
        data = self.api({"action": "add_edge", "source": a, "target": b}).json()

        self.api({"action": "delete_edge", "edge_id": data["workflow"]["edges"][0]["id"]})

        self.assertFalse(self.workflow.edges.exists())

    def test_deleting_a_step_removes_its_edges(self):
        a, b = self.add("A"), self.add("B")

        self.api({"action": "add_edge", "source": a, "target": b})
        self.api({"action": "delete_step", "step_id": a})

        self.assertFalse(self.workflow.edges.exists())


class WorkflowElnIntegrationTests(WorkflowBase):
    def test_import_eln_steps_chains_them_and_stays_in_sync(self):
        entry = NotebookEntry.objects.create(title="Gel", author=self.ana)
        composer.add_step(entry, "Pour gel")
        composer.add_step(entry, "Load samples", deadline="2026-12-02T10:00")

        response = self.api({"action": "import_eln", "entry": entry.pk})
        data = response.json()["workflow"]

        self.assertEqual([s["title"] for s in data["steps"]], ["Pour gel", "Load samples"])
        self.assertEqual(len(data["edges"]), 1)
        self.assertTrue(data["steps"][0]["from_eln"])
        self.assertEqual(data["steps"][0]["entry"], entry.pk)

        again = self.api({"action": "import_eln", "entry": entry.pk}).json()["workflow"]

        self.assertEqual(len(again["steps"]), 2)

        self.api({"action": "update_step", "step_id": data["steps"][0]["id"], "step": {"status": "done"}})

        self.assertTrue(entry.steps.get(body="Pour gel").finished)

        self.api({"action": "update_step", "step_id": data["steps"][0]["id"], "step": {"status": "doing"}})

        self.assertFalse(entry.steps.get(body="Pour gel").finished)

    def test_cannot_import_an_entry_the_user_cannot_see(self):
        entry = NotebookEntry.objects.create(title="Private", author=self.bia)

        self.assertEqual(self.api({"action": "import_eln", "entry": entry.pk}).status_code, 400)

    def test_lookup_returns_visible_records_only(self):
        NotebookEntry.objects.create(title="Gel mine", author=self.ana)
        NotebookEntry.objects.create(title="Gel theirs", author=self.bia)

        results = self.client.get(reverse("workflow_lookup_api"), {"kind": "eln", "q": "Gel"}).json()["results"]

        self.assertEqual(len(results), 1)
        self.assertIn("Gel mine", results[0]["label"])
        self.assertEqual(self.client.get(reverse("workflow_lookup_api"), {"kind": "zzz"}).status_code, 404)


class WorkflowWiringTests(WorkflowBase):
    def test_detail_page_loads_editor_assets_and_data(self):
        self.add("A")

        page = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertContains(page, "workflow_editor.js")
        self.assertContains(page, 'id="wf-data"')
        self.assertContains(page, 'data-can-edit="1"')

    def test_sidebar_and_hub_link_to_workflows(self):
        self.assertContains(self.client.get(reverse("workflow_list")), reverse("workflow_list"))

        hub = self.client.get(reverse("bench:home"))

        self.assertContains(hub, reverse("workflow_list"))

    def test_workflow_changes_are_in_the_activity_history(self):
        from core.models.activity import ActivityLog

        self.assertTrue(ActivityLog.objects.filter(entity_type="workflow", verb="created").exists())


class WorkflowJupyterStepTests(WorkflowBase):
    def setUp(self):
        super().setUp()

        from core.models.lab_tools.notebook import JupyterNotebook

        self.mine = JupyterNotebook.objects.create(title="Align reads", owner=self.ana, notebook_json={"cells": []})
        self.theirs = JupyterNotebook.objects.create(title="Private", owner=self.bia, notebook_json={"cells": []})

    def test_a_step_links_a_notebook_with_parameters_and_a_result_note(self):
        sid = self.add("Align", kind="jupyter", jupyter_notebook=self.mine.pk, parameters="taxid=1280\nmin_length = 200", result_note="Saved in /scratch/x")
        step = self.client.get(reverse("workflow_detail", args=[self.workflow.pk])).context["workflow_data"]["steps"][0]

        self.assertEqual(step["kind"], "jupyter")
        self.assertEqual(step["jupyter_notebook"], self.mine.pk)
        self.assertEqual(step["jupyter_label"], "Align reads")
        self.assertTrue(step["jupyter_url"].endswith(f"/{self.mine.pk}/"))
        self.assertEqual(step["parameters"], "taxid=1280\nmin_length=200")
        self.assertEqual(step["result_note"], "Saved in /scratch/x")
        self.assertEqual(WorkflowStep.objects.get(pk=sid).config["parameters"], {"taxid": "1280", "min_length": "200"})

    def test_notebook_must_belong_to_the_user_and_parameters_are_validated(self):
        sid = self.add("Align", kind="jupyter")

        def update(**fields):
            return self.api({"action": "update_step", "step_id": sid, "step": fields})

        self.assertEqual(update(jupyter_notebook=self.theirs.pk).status_code, 400)
        self.assertEqual(update(parameters="no equals sign").status_code, 400)
        self.assertEqual(update(parameters="1bad=x").status_code, 400)
        self.assertEqual(update(parameters="; rm -rf=x").status_code, 400)
        self.assertEqual(update(parameters="\n".join(f"p{i}=v" for i in range(21))).status_code, 400)
        self.assertEqual(update(parameters="k=" + "x" * 201).status_code, 400)
        self.assertEqual(update(jupyter_notebook=self.mine.pk).status_code, 200)
        self.assertEqual(update(jupyter_notebook=None).status_code, 200)
        self.assertNotIn("notebook_id", WorkflowStep.objects.get(pk=sid).config)

    def test_lookup_lists_only_own_notebooks(self):
        results = self.client.get(reverse("workflow_lookup_api"), {"kind": "jupyter", "q": ""}).json()["results"]

        self.assertEqual([r["label"] for r in results], ["Align reads"])
