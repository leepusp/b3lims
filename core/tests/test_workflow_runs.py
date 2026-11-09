import base64
import json
import subprocess
from pathlib import Path
from unittest import mock

from core.models.lab_tools.notebook import JupyterNotebook
from core.models.lab_tools.workflow import WorkflowStepRun
from core.services import jupyter_server
from core.tests.test_workflow import WorkflowBase

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
RUNNER = "core.services.jupyter_server._run_server_runner"


class WorkflowRunTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        self.nb = JupyterNotebook.objects.create(title="Align", owner=self.ana, notebook_json={"cells": []})
        self.step = self.add("Align reads", kind="jupyter", jupyter_notebook=self.nb.pk, parameters="taxid=1280")

    def run_api(self, action, **extra):
        return self.api({"action": action, **extra})

    def start(self, **extra):
        reply = {"run_id": "run_20261109T000000Z_1_2", "job_id": "123", "slurm_user": "ana"}

        with mock.patch(RUNNER, return_value=reply) as runner:
            response = self.run_api("run_step", step_id=self.step, **extra)

        return response, runner

    def test_start_submits_with_parameters_and_marks_step_doing(self):
        response, runner = self.start(resources={"cpus": 4, "memory_mb": 8192, "minutes": 30})

        self.assertEqual(response.status_code, 200, response.content)

        args = runner.call_args.args

        self.assertEqual(args[:2], ("run-start", self.nb.pk))
        self.assertEqual(args[4:9], (4, 8192, 30, "basic", "auto"))
        self.assertEqual(json.loads(base64.b64decode(args[9])), {"taxid": "1280"})

        step = next(s for s in response.json()["workflow"]["steps"] if s["id"] == self.step)

        self.assertEqual(step["status"], "doing")
        self.assertEqual(step["run"]["state"], "submitted")

    def test_second_run_is_refused_while_one_is_active(self):
        self.start()

        response, runner = self.start()

        self.assertEqual(response.status_code, 400)
        runner.assert_not_called()

    def test_invalid_resources_and_missing_notebook_are_refused(self):
        with mock.patch(RUNNER) as runner:
            self.assertEqual(self.run_api("run_step", step_id=self.step, resources={"cpus": 0}).status_code, 400)
            self.assertEqual(self.run_api("run_step", step_id=self.step, resources={"partition": "x"}).status_code, 400)

            manual = self.add("Manual")

            self.assertEqual(self.run_api("run_step", step_id=manual).status_code, 400)
            runner.assert_not_called()

    def test_runner_failure_is_reported_and_creates_no_run(self):
        with mock.patch(RUNNER, side_effect=jupyter_server.JupyterNotebookError("no notebook file")):
            response = self.run_api("run_step", step_id=self.step)

        self.assertEqual(response.status_code, 400)
        self.assertIn("no notebook file", response.json()["message"])
        self.assertEqual(WorkflowStepRun.objects.count(), 0)

    def refresh(self, state, result=None):
        run = WorkflowStepRun.objects.get()

        with mock.patch(RUNNER, return_value={"status": "ok", "state": state, "result": result or {}, "log_tail": "log"}):
            self.assertEqual(self.run_api("refresh_run", run_id=run.pk).status_code, 200)

        run.refresh_from_db()
        self.step_obj = run.step
        self.step_obj.refresh_from_db()

        return run

    def test_completed_run_marks_step_done(self):
        self.start()

        run = self.refresh("COMPLETED", {"status": "completed", "cells": 3, "executed": 3, "seconds": 2.5})

        self.assertEqual(run.state, "completed")
        self.assertEqual(self.step_obj.status, "done")
        self.assertIsNotNone(run.finished_at)

    def test_notebook_failure_blocks_step_even_if_slurm_says_completed(self):
        self.start()

        run = self.refresh("COMPLETED", {"status": "failed", "error": "ValueError: boom"})

        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error, "ValueError: boom")
        self.assertEqual(self.step_obj.status, "blocked")

    def test_running_and_unknown_states_keep_run_active(self):
        self.start()

        self.assertEqual(self.refresh("RUNNING").state, "running")
        self.assertEqual(self.refresh("UNKNOWN").state, "running")
        self.assertEqual(self.step_obj.status, "doing")

    def test_cancel_marks_run_cancelled(self):
        self.start()

        run = WorkflowStepRun.objects.get()

        with mock.patch(RUNNER, return_value={"status": "cancelled"}) as runner:
            self.assertEqual(self.run_api("cancel_run", run_id=run.pk).status_code, 200)

        self.assertEqual(runner.call_args.args[0], "run-cancel")

        run.refresh_from_db()

        self.assertEqual(run.state, "cancelled")

    def test_non_members_cannot_use_runs(self):
        self.start()

        run = WorkflowStepRun.objects.get()

        with mock.patch(RUNNER) as runner:
            self.assertEqual(self.api({"action": "cancel_run", "run_id": run.pk}, user=self.bia).status_code, 404)
            runner.assert_not_called()


class BrokerScriptTests(WorkflowBase):
    """The root scripts cannot run here (no Slurm), but they must parse and refuse bad input."""

    def test_scripts_are_valid_bash(self):
        for name in ("sbin/biobank-jupyter-server-broker", "runtime/notebook_run.sh", "runtime/notebook_server.sh"):
            result = subprocess.run(["bash", "-n", str(DEPLOY / name)], capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_broker_dispatches_run_actions(self):
        text = (DEPLOY / "sbin/biobank-jupyter-server-broker").read_text()

        for action in ("run-start", "run-status", "run-cancel"):
            self.assertIn(f"{action})", text)

    def test_broker_has_outputs_action_and_runner_collects_figures(self):
        self.assertIn("run-outputs)", (DEPLOY / "sbin/biobank-jupyter-server-broker").read_text())
        self.assertIn("image/png", (DEPLOY / "runtime/notebook_run.sh").read_text())

    def test_runner_script_mounts_repository_read_only(self):
        for name in ("runtime/notebook_run.sh", "runtime/notebook_server.sh"):
            text = (DEPLOY / name).read_text()

            self.assertIn('--ro-bind "$REPOSITORY_ROOT" "$REPOSITORY_ROOT"', text)


class WorkflowRunResourcesTests(WorkflowRunTests):
    def test_partition_node_are_sent_and_remembered(self):
        response, runner = self.start(resources={"partition": "max50", "node": "gn03", "cpus": 1, "memory_mb": 2048, "minutes": 10})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(runner.call_args.args[4:9], (1, 2048, 10, "max50", "gn03"))

        step = next(s for s in response.json()["workflow"]["steps"] if s["id"] == self.step)

        self.assertEqual(step["run_resources"]["partition"], "max50")
        self.assertEqual(step["run_resources"]["node"], "gn03")

    def test_time_limit_follows_the_partition(self):
        with mock.patch(RUNNER) as runner:
            too_long = self.run_api("run_step", step_id=self.step, resources={"partition": "basic", "minutes": 72 * 60 + 1})

            self.assertEqual(too_long.status_code, 400)
            runner.assert_not_called()


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 20).decode()


class WorkflowRunOutputsTests(WorkflowRunTests):
    def finish_with_outputs(self, outputs):
        self.start()

        run = WorkflowStepRun.objects.get()
        replies = [
            {"status": "ok", "state": "COMPLETED", "result": {"status": "completed", "seconds": 3}, "log_tail": ""},
            {"status": "ok", "outputs": outputs},
        ]

        with mock.patch(RUNNER, side_effect=replies) as runner:
            response = self.run_api("refresh_run", run_id=run.pk)

        self.assertEqual([c.args[0] for c in runner.call_args_list], ["run-status", "run-outputs"])
        run.refresh_from_db()

        return run, response

    def test_outputs_are_stored_and_listed_on_the_step(self):
        run, response = self.finish_with_outputs({"cells": [{"cell": 1, "text": "taxid = 1280", "images": [PNG]}]})
        step = next(s for s in response.json()["workflow"]["steps"] if s["id"] == self.step)

        self.assertEqual(run.outputs["cells"][0]["text"], "taxid = 1280")
        self.assertEqual(step["run"]["output_text"], "taxid = 1280")
        self.assertEqual(step["run"]["duration"], 3)
        self.assertEqual(len(step["run"]["images"]), 1)

    def test_figure_is_served_as_png_to_members_only(self):
        run, response = self.finish_with_outputs({"cells": [{"cell": 1, "text": "", "images": [PNG]}]})
        url = response.json()["workflow"]["steps"][0]["run"]["images"][0]
        served = self.client.get(url)

        self.assertEqual(served.status_code, 200)
        self.assertEqual(served["Content-Type"], "image/png")
        self.assertEqual(served["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.client.get(url.replace("/figure/0.png", "/figure/5.png")).status_code, 404)

        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_data_that_is_not_a_png_is_never_served(self):
        fake = base64.b64encode(b"<html>not a png</html>").decode()
        run, response = self.finish_with_outputs({"cells": [{"cell": 1, "text": "", "images": [fake, "%%%"]}]})

        self.assertEqual(self.client.get(response.json()["workflow"]["steps"][0]["run"]["images"][0]).status_code, 404)
        self.assertEqual(self.client.get(response.json()["workflow"]["steps"][0]["run"]["images"][1]).status_code, 404)

    def test_missing_outputs_do_not_break_the_refresh(self):
        self.start()

        run = WorkflowStepRun.objects.get()
        replies = [
            {"status": "ok", "state": "COMPLETED", "result": {"status": "completed"}, "log_tail": ""},
            jupyter_server.JupyterNotebookError("gone"),
        ]

        with mock.patch(RUNNER, side_effect=replies):
            self.assertEqual(self.run_api("refresh_run", run_id=run.pk).status_code, 200)

        run.refresh_from_db()

        self.assertEqual(run.state, "completed")
        self.assertEqual(run.outputs, {})
