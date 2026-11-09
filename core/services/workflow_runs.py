"""Unattended notebook runs for Workflow steps (via the Jupyter broker)."""

from __future__ import annotations

import base64
import binascii
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models.lab_tools.workflow import WorkflowStepRun
from core.services import jupyter_server as jupyter

ACTIVE = (WorkflowStepRun.State.SUBMITTED, WorkflowStepRun.State.RUNNING)
DEFAULTS = {"cpus": 2, "memory_mb": 4096, "minutes": 60, "partition": "basic", "node": "auto"}
SLURM_TO_STATE = {
    "PENDING": "submitted", "CONFIGURING": "submitted", "RUNNING": "running", "COMPLETING": "running",
    "COMPLETED": "completed", "CANCELLED": "cancelled", "FAILED": "failed", "TIMEOUT": "failed",
    "OUT_OF_MEMORY": "failed", "NODE_FAIL": "failed", "BOOT_FAIL": "failed", "DEADLINE": "failed",
}


def _resources(data):
    values = {**DEFAULTS, **{k: v for k, v in (data or {}).items() if k in DEFAULTS and v not in (None, "")}}

    try:
        cpus, memory, minutes = int(values["cpus"]), int(values["memory_mb"]), int(values["minutes"])
    except (TypeError, ValueError):
        raise ValidationError("CPU, memory and time must be numbers.")

    partitions = tuple(getattr(settings, "BIOBANK_JUPYTER_PARTITIONS", ("basic", "max50")))
    nodes = tuple(getattr(settings, "BIOBANK_JUPYTER_NODES", ("n01", "gn01", "gn02", "gn03")))
    hours = dict(getattr(settings, "BIOBANK_JUPYTER_PARTITION_MAX_HOURS", {"basic": 72, "max50": 168}))
    partition, node = str(values["partition"]), str(values["node"] or "auto")

    if partition not in partitions:
        raise ValidationError("Invalid Slurm partition.")
    if node != "auto" and node not in nodes:
        raise ValidationError("Invalid compute node.")
    if not 1 <= cpus <= 128:
        raise ValidationError("CPU cores must be between 1 and 128.")
    if not 1024 <= memory <= 1048576:
        raise ValidationError("Memory must be between 1024 and 1048576 MB.")
    if not 1 <= minutes <= int(hours.get(partition, 168)) * 60:
        raise ValidationError("Time is outside the limit of this partition.")

    return {"cpus": cpus, "memory_mb": memory, "minutes": minutes, "partition": partition, "node": node}


def active_run(step):
    return step.runs.filter(state__in=ACTIVE).first()


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def run_images(run):
    return [image for cell in (run.outputs or {}).get("cells", []) for image in cell.get("images", [])]


def run_image_bytes(run, index):
    """PNG bytes of figure ``index`` or None (checked again when served)."""
    images = run_images(run)

    if not 0 <= index < len(images):
        return None

    try:
        data = base64.b64decode(images[index], validate=True)
    except (binascii.Error, ValueError):
        return None

    return data if data.startswith(PNG_SIGNATURE) else None


def run_tables(run):
    tables = [t for c in (run.outputs or {}).get("cells", []) for t in c.get("tables", [])]

    return tables[:3]


def _output_text(run):
    text = "\n".join(c.get("text", "").strip() for c in (run.outputs or {}).get("cells", []) if c.get("text"))

    return text[:3000]


def serialize_run(run):
    from django.urls import reverse

    count = len(run_images(run))

    return {
        "images": [
            reverse("workflow_run_image", args=[run.step.workflow_id, run.pk, i]) for i in range(count)
        ],
        "output_text": _output_text(run),
        "tables": run_tables(run),
        "duration": (run.result or {}).get("seconds"),
        "resources": (run.step.config or {}).get("run_resources") or {},
        "id": run.pk,
        "state": run.state,
        "job_id": run.job_id,
        "error": run.error,
        "result": run.result,
        "log_tail": run.log_tail[-2000:],
        "started_by": run.started_by.get_username() if run.started_by else "",
        "created_at": timezone.localtime(run.created_at).strftime("%Y-%m-%d %H:%M"),
        "finished_at": timezone.localtime(run.finished_at).strftime("%Y-%m-%d %H:%M") if run.finished_at else "",
    }


def _apply_step_status(step, state):
    from core.services import workflow as workflow_service

    new = {"submitted": "doing", "running": "doing", "completed": "done"}.get(state, "blocked")

    if step.status != new:
        workflow_service.apply_step_fields(step, None, {"status": new})
        step.save()
        workflow_service.sync_notebook_step(step, step.workflow.owner)


def start_run(step, user, resources=None):
    """Submit the step's notebook; the step goes to "doing"."""
    config = step.config or {}

    if step.kind != "jupyter" or not config.get("notebook_id"):
        raise ValidationError("Choose a Jupyter notebook for this step first.")
    if active_run(step):
        raise ValidationError("This step already has a run in progress.")

    notebook = jupyter.visible_notebooks_for_user(user).filter(pk=config["notebook_id"]).first()

    if not notebook:
        raise ValidationError("That Jupyter notebook is not available.")
    if not jupyter.can_edit_notebook(user, notebook):
        raise ValidationError("You cannot run this notebook.")
    if notebook.owner_id is None:
        raise ValidationError("The notebook does not have an owner.")

    resources = _resources(resources)
    parameters = dict(config.get("parameters") or {})
    encoded = base64.b64encode(json.dumps(parameters).encode()).decode() if parameters else "-"
    owner = jupyter._safe_username(notebook.owner.get_username())

    try:
        response = jupyter._run_server_runner(
            "run-start", notebook.pk, notebook.owner_id, owner, resources["cpus"], resources["memory_mb"],
            resources["minutes"], resources["partition"], resources["node"], encoded,
        )
    except jupyter.JupyterNotebookError as exc:
        raise ValidationError(str(exc))

    run_id, job_id = str(response.get("run_id") or ""), str(response.get("job_id") or "")

    if not jupyter.RUN_ID_RE.fullmatch(run_id) or not job_id.isdigit():
        raise ValidationError("The runner returned an invalid answer.")

    step.config = {**config, "run_resources": resources}
    step.save(update_fields=["config"])

    run = WorkflowStepRun.objects.create(
        step=step, notebook=notebook, started_by=user, run_id=run_id, job_id=job_id, parameters=parameters
    )

    _apply_step_status(step, "submitted")

    return run


def _fetch_outputs(run, owner):
    try:
        response = jupyter._run_server_runner("run-outputs", run.notebook_id, owner, run.run_id, timeout=60)
    except jupyter.JupyterNotebookError:
        return {}

    outputs = response.get("outputs")

    return outputs if isinstance(outputs, dict) else {}


def refresh_run(run):
    """Ask the broker for the state; finished runs update the step once."""
    if run.state not in ACTIVE or not run.notebook:
        return run

    owner = jupyter._safe_username(run.notebook.owner.get_username())

    try:
        response = jupyter._run_server_runner("run-status", run.notebook_id, owner, run.run_id)
    except jupyter.JupyterNotebookError as exc:
        run.error = str(exc)[:500]
        run.save(update_fields=["error"])

        return run

    state = SLURM_TO_STATE.get(str(response.get("state") or "").upper().split()[0], run.state)
    result = response.get("result") if isinstance(response.get("result"), dict) else {}

    if state == "completed" and result.get("status") == "failed":
        state = "failed"
    if state == "completed" and result.get("status") != "completed":
        state = "failed"
        result = result or {"status": "failed", "error": "The job ended without a result."}

    run.state = state
    run.result = result
    run.log_tail = str(response.get("log_tail") or "")[-4000:]
    run.error = str(result.get("error") or "")[:500] if state == "failed" else ""

    if state not in ("submitted", "running"):
        run.finished_at = timezone.now()
        run.outputs = _fetch_outputs(run, owner)
        _apply_step_status(run.step, state)

    run.save()

    return run


def cancel_run(run):
    if run.state not in ACTIVE or not run.notebook:
        raise ValidationError("This run is not active.")

    owner = jupyter._safe_username(run.notebook.owner.get_username())

    try:
        jupyter._run_server_runner("run-cancel", run.notebook_id, owner, run.run_id)
    except jupyter.JupyterNotebookError as exc:
        raise ValidationError(str(exc))

    run.state, run.finished_at = "cancelled", timezone.now()
    run.save(update_fields=["state", "finished_at"])
    _apply_step_status(run.step, "cancelled")

    return run
