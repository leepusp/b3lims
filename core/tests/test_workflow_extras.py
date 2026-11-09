"""Workflow notes, attached images, result tables and previews of linked records."""

import base64
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from core.models.lab_tools.notebook import JupyterNotebook, MolecularFeature, MolecularSequence, NotebookEntry
from core.models.lab_tools.workflow import WorkflowStepFile, WorkflowStepRun
from core.services import workflow_runs
from core.tests.test_workflow import WorkflowBase

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
RUNNER = "core.services.jupyter_server._run_server_runner"


def step_of(response, step_id):
    return next(s for s in response.json()["workflow"]["steps"] if s["id"] == step_id)


class NoteTests(WorkflowBase):
    def test_note_ignores_status_owner_deadline_and_links(self):
        entry = NotebookEntry.objects.create(title="Mine", author=self.ana)
        note = self.add(
            "Remember", kind="note", notes="Check the primers", status="done", assignee=self.bia.pk,
            due_date="2030-01-01T10:00", entry=entry.pk,
        )
        data = step_of(self.api({"action": "update_step", "step_id": note, "step": {"notes": "x"}}), note)

        self.assertEqual(data["kind"], "note")
        self.assertEqual(data["status"], "todo")
        self.assertEqual(data["assignee"], None)
        self.assertEqual(data["due_date"], "")
        self.assertEqual(data["entry"], None)
        self.assertEqual(data["notes"], "x")

    def test_note_cannot_be_connected(self):
        note = self.add("Note", kind="note")
        step = self.add("Work")

        self.assertEqual(self.api({"action": "add_edge", "source": step, "target": note}).status_code, 400)
        self.assertEqual(self.api({"action": "add_edge", "source": note, "target": step}).status_code, 400)

    def test_notes_do_not_count_as_progress(self):
        self.add("Note", kind="note")
        done = self.add("Work", status="done")
        workflow = self.api({"action": "update_step", "step_id": done, "step": {}}).json()["workflow"]

        self.assertEqual(workflow["counts"], {"todo": 0, "doing": 0, "done": 1, "blocked": 0})

        listing = self.client.get(reverse("workflow_list"))
        row = next(w for w in listing.context["workflows"] if w.pk == self.workflow.pk)

        self.assertEqual((row.step_total, row.step_done), (1, 1))

    def test_a_step_turned_into_a_note_loses_its_status(self):
        step = self.add("Work", status="blocked")
        data = step_of(self.api({"action": "update_step", "step_id": step, "step": {"kind": "note"}}), step)

        self.assertEqual(data["status"], "todo")

    def test_note_with_a_due_date_never_reaches_the_calendar(self):
        from core.models.lab_tools.workflow import WorkflowStep

        self.add("Note", kind="note", due_date="2030-01-01T10:00")

        self.assertFalse(WorkflowStep.objects.filter(kind="note", due_date__isnull=False).exists())


class AttachedImageTests(WorkflowBase):
    def upload(self, step, content=PNG, name="gel.png", user=None):
        if user:
            self.client.force_login(user)

        return self.client.post(
            reverse("workflow_step_file_upload", args=[self.workflow.pk, step]),
            {"file": SimpleUploadedFile(name, content)},
        )

    def test_png_is_stored_listed_and_served_safely(self):
        step = self.add("Gel")
        response = self.upload(step)

        self.assertEqual(response.status_code, 200, response.content)

        item = step_of(response, step)["files"][0]
        served = self.client.get(item["url"])

        self.assertEqual(served.status_code, 200)
        self.assertEqual(served["Content-Type"], "image/png")
        self.assertEqual(served["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", served["Content-Security-Policy"])
        self.assertEqual(served.content, PNG)

    def test_only_real_images_are_accepted(self):
        step = self.add("Gel")

        for content, name in [
            (b"<html><script>alert(1)</script></html>", "x.png"),
            (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "x.svg"),
            (b"", "empty.png"),
            (b"%PDF-1.4", "doc.png"),
        ]:
            self.assertEqual(self.upload(step, content, name).status_code, 400, name)

        self.assertEqual(WorkflowStepFile.objects.count(), 0)

    def test_size_and_count_limits(self):
        step = self.add("Gel")

        self.assertEqual(self.upload(step, PNG + b"0" * (3 * 1024 * 1024)).status_code, 400)

        for _ in range(8):
            self.assertEqual(self.upload(step).status_code, 200)

        self.assertEqual(self.upload(step).status_code, 400)

    def test_notes_do_not_take_images(self):
        self.assertEqual(self.upload(self.add("Note", kind="note")).status_code, 400)

    def test_file_names_are_sanitised(self):
        step = self.add("Gel")
        data = step_of(self.upload(step, name="../../etc/<b>x</b>.png"), step)

        self.assertNotIn("/", data["files"][0]["name"])
        self.assertNotIn("<", data["files"][0]["name"])

    def test_access_rules(self):
        step = self.add("Gel")
        item = step_of(self.upload(step), step)["files"][0]

        self.client.force_login(self.cris)

        self.assertEqual(self.client.get(item["url"]).status_code, 404)
        self.assertEqual(self.upload(step, user=self.cris).status_code, 404)

        self.workflow.members.add(self.bia)
        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(item["url"]).status_code, 200)

        self.client.logout()

        self.assertEqual(self.client.get(item["url"]).status_code, 302)

    def test_delete_is_limited_to_this_workflow(self):
        from core.models.lab_tools.workflow import Workflow

        step = self.add("Gel")
        file_id = step_of(self.upload(step), step)["files"][0]["id"]
        other = Workflow.objects.create(name="Other", owner=self.ana)

        self.assertEqual(self.api({"action": "delete_file", "file_id": file_id}, workflow=other).status_code, 404)
        self.assertEqual(WorkflowStepFile.objects.count(), 1)
        self.assertEqual(self.api({"action": "delete_file", "file_id": file_id}).status_code, 200)
        self.assertEqual(WorkflowStepFile.objects.count(), 0)

    def test_get_is_not_allowed_on_the_upload_endpoint(self):
        step = self.add("Gel")

        self.assertEqual(self.client.get(reverse("workflow_step_file_upload", args=[self.workflow.pk, step])).status_code, 405)


class PreviewTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        self.molecule = MolecularSequence.objects.create(
            name="pUC19", owner=self.ana, sequence="ATGC" * 10, length=40, topology="circular"
        )
        MolecularFeature.objects.create(molecule=self.molecule, name="lacZ", start=5, end=30, color="#ff0000")
        self.entry = NotebookEntry.objects.create(title="Cloning day", author=self.ana)

    def test_owner_sees_molecule_and_entry_previews(self):
        step = self.add("Clone", molecule=self.molecule.pk, entry=self.entry.pk)
        data = step_of(self.api({"action": "update_step", "step_id": step, "step": {}}), step)
        preview = data["preview"]

        self.assertEqual(preview["molecule"]["name"], "pUC19")
        self.assertEqual(preview["molecule"]["length"], 40)
        self.assertEqual(preview["molecule"]["features"][0]["n"], "lacZ")
        self.assertEqual(preview["entry"]["title"], "Cloning day")

    def test_a_member_without_access_gets_no_preview_of_private_records(self):
        step = self.add("Clone", molecule=self.molecule.pk, entry=self.entry.pk)

        self.workflow.members.add(self.bia)
        self.client.force_login(self.bia)

        data = step_of(self.api({"action": "update_step", "step_id": step, "step": {"title": "Renamed"}}), step)

        self.assertEqual(data["preview"], {})
        # The link itself is still there; only the details stay hidden.
        self.assertEqual(data["molecule"], self.molecule.pk)

    def test_detail_page_embeds_previews_for_the_viewer_only(self):
        self.add("Clone", molecule=self.molecule.pk)

        page = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertContains(page, "pUC19")

        self.workflow.members.add(self.bia)
        self.client.force_login(self.bia)

        self.assertNotContains(self.client.get(reverse("workflow_detail", args=[self.workflow.pk])), "pUC19")

    def test_feature_list_is_capped(self):
        for i in range(30):
            MolecularFeature.objects.create(molecule=self.molecule, name=f"f{i}", start=i + 1, end=i + 2)

        step = self.add("Clone", molecule=self.molecule.pk)
        data = step_of(self.api({"action": "update_step", "step_id": step, "step": {}}), step)

        self.assertLessEqual(len(data["preview"]["molecule"]["features"]), 14)


class ResultTableTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        self.nb = JupyterNotebook.objects.create(title="Reads", owner=self.ana, notebook_json={"cells": []})
        self.step = self.add("Count", kind="jupyter", jupyter_notebook=self.nb.pk)

    def finish(self, outputs):
        with mock.patch(RUNNER, return_value={"run_id": "r1", "job_id": "9", "slurm_user": "ana"}):
            self.api({"action": "run_step", "step_id": self.step})

        run = WorkflowStepRun.objects.get()
        replies = [
            {"status": "ok", "state": "COMPLETED", "result": {"status": "completed"}, "log_tail": ""},
            {"status": "ok", "outputs": outputs},
        ]

        with mock.patch(RUNNER, side_effect=replies):
            response = self.api({"action": "refresh_run", "run_id": run.pk})

        return step_of(response, self.step)

    def test_tables_reach_the_step(self):
        table = [["contig", "reads"], ["c1", "10"], ["c2", "20"]]
        data = self.finish({"cells": [{"cell": 1, "text": "", "images": [], "tables": [table]}]})

        self.assertEqual(data["run"]["tables"], [table])

    def test_at_most_three_tables_are_returned(self):
        cells = [{"cell": i, "text": "", "images": [], "tables": [[["a"], ["1"]]]} for i in range(6)]

        self.assertEqual(len(self.finish({"cells": cells})["run"]["tables"]), 3)

    def test_runs_without_tables_still_work(self):
        data = self.finish({"cells": [{"cell": 1, "text": "hello", "images": []}]})

        self.assertEqual(data["run"]["tables"], [])
        self.assertEqual(data["run"]["output_text"], "hello")


def _extract(path, start, end):
    text = (DEPLOY / path).read_text()

    return text[text.index(start): text.index(end)]


class RunnerScriptTests(WorkflowBase):
    def parse_table(self, html):
        namespace = {"HTMLParser": HTMLParser}

        exec(_extract("runtime/notebook_run.sh", "class TableParser", "def collect_outputs"), namespace)

        return namespace["parse_table"](html)

    def test_table_parser_returns_plain_text_only(self):
        rows = self.parse_table(
            "<table><thead><tr><th></th><th>x&lt;b&gt;</th></tr></thead>"
            "<tbody><tr><td>0</td><td><b>bold</b> <script>alert(1)</script></td></tr></tbody></table>"
        )

        self.assertEqual(rows[0], ["", "x<b>"])
        self.assertEqual(rows[1][0], "0")
        self.assertNotIn("<b>", rows[1][1])

    def test_table_parser_limits_and_ignores_nested_tables(self):
        body = "".join("<tr>" + "<td>%s</td>" % ("v" * 200) * 20 + "</tr>" for _ in range(50))
        rows = self.parse_table("<table>" + body + "<tr><td><table><tr><td>inner</td></tr></table></td></tr></table>")

        self.assertLessEqual(len(rows), 21)
        self.assertLessEqual(max(len(r) for r in rows), 12)
        self.assertNotIn("inner", json.dumps(rows))

    def test_table_parser_survives_broken_html(self):
        self.assertEqual(self.parse_table("<table><tr><td>a"), [])
        self.assertEqual(self.parse_table("not html"), [])

    def test_broker_output_validator_trims_and_rejects(self):
        code = re.search(
            r'run_outputs\(\) \{.*?"\$PYTHON" -c \'\n(.*?)\n\'\n\}',
            (DEPLOY / "sbin/biobank-jupyter-server-broker").read_text(),
            re.S,
        ).group(1)
        png = base64.b64encode(PNG).decode()
        big = [["x" * 500] * 40] * 60
        payload = {"cells": [{"cell": 1, "text": "t" * 5000, "images": [png, "<script>", 5], "tables": [big]}]}

        def run(stdin):
            result = subprocess.run(["python3", "-c", code], input=stdin, text=True, capture_output=True)

            self.assertEqual(result.returncode, 0, result.stderr)

            return json.loads(result.stdout)["outputs"]["cells"]

        cell = run(json.dumps(payload))[0]

        self.assertEqual(cell["images"], [png])
        self.assertEqual(len(cell["text"]), 1500)
        self.assertEqual((len(cell["tables"][0]), len(cell["tables"][0][0]), len(cell["tables"][0][0][0])), (21, 12, 80))
        self.assertEqual(run("garbage"), [])
        self.assertEqual(run(""), [])
        self.assertEqual(run(json.dumps({"cells": "nope"})), [])


class PrivacyOfLinksTests(WorkflowBase):
    def test_member_does_not_learn_names_of_records_they_cannot_open(self):
        private_nb = JupyterNotebook.objects.create(title="Secret analysis", owner=self.ana, notebook_json={})
        entry = NotebookEntry.objects.create(title="Secret experiment", author=self.ana)
        molecule = MolecularSequence.objects.create(name="SecretPlasmid", owner=self.ana, sequence="ATGC", length=4)
        step = self.add("Work", kind="jupyter", jupyter_notebook=private_nb.pk, molecule=molecule.pk)

        self.api({"action": "update", "entry": entry.pk})
        self.workflow.members.add(self.bia)
        self.client.force_login(self.bia)

        page = self.client.get(reverse("workflow_detail", args=[self.workflow.pk])).content.decode()
        reply = self.api({"action": "update_step", "step_id": step, "step": {"title": "Renamed"}})

        for secret in ("Secret analysis", "Secret experiment", "SecretPlasmid"):
            self.assertNotIn(secret, page)
            self.assertNotIn(secret, reply.content.decode())

        self.assertIn("Private record", page)

    def test_the_owner_still_sees_everything(self):
        molecule = MolecularSequence.objects.create(name="MyPlasmid", owner=self.ana, sequence="ATGC", length=4)

        self.add("Work", molecule=molecule.pk)

        self.assertContains(self.client.get(reverse("workflow_detail", args=[self.workflow.pk])), "MyPlasmid")
