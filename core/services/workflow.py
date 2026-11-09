"""Workflow service: access rules, validation and serialisation for the flow editor."""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core.models.lab_tools.workflow import Workflow, WorkflowEdge, WorkflowStep
from core.services.notebook_composer import _parse_deadline

MAX_STEPS = 200
FIELD_LIMITS = {"title": 200, "notes": 5000, "name": 200, "description": 5000, "result_note": 5000}
PARAM_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
MAX_PARAMS = 20


def visible_workflows(user):
    if user.is_superuser:
        return Workflow.objects.all()

    return Workflow.objects.filter(Q(owner=user) | Q(members=user)).distinct()


def can_edit(user, workflow):
    return user.is_superuser or workflow.owner_id == user.pk or workflow.members.filter(pk=user.pk).exists()


def _text(value, field, required=False):
    value = str(value or "").strip()

    if required and not value:
        raise ValidationError(f"{field.capitalize()} is required.")
    if len(value) > FIELD_LIMITS[field]:
        raise ValidationError(f"{field.capitalize()} is too long.")

    return value


def _choice(value, choices, label):
    if value not in {c[0] for c in choices}:
        raise ValidationError(f"Invalid {label}.")

    return value


# --- link resolution ---------------------------------------------------------


def _entry_for(user, pk):
    from core.permissions.notebook import visible_notebook_entries_for_user

    entry = visible_notebook_entries_for_user(user).filter(pk=pk).first()

    if not entry:
        raise ValidationError("That ELN entry is not available.")

    return entry


def _molecule_for(user, pk):
    from core.views.internal.lab_tools.notebook import _visible_molecular_sequences_for_user

    molecule = _visible_molecular_sequences_for_user(user).filter(pk=pk).first()

    if not molecule:
        raise ValidationError("That molecular record is not available.")

    return molecule


def _sample_for(user, pk):
    from core.permissions.samples import visible_samples_for_user

    sample = visible_samples_for_user(user).filter(pk=pk).first()

    if not sample:
        raise ValidationError("That sample is not available.")

    return sample


def _link(value, resolver, user):
    if value in (None, "", 0):
        return None

    try:
        return resolver(user, int(value))
    except (TypeError, ValueError):
        raise ValidationError("Invalid link.")


# --- step operations ---------------------------------------------------------


def _notebook_for(user, pk):
    from core.services.jupyter_server import visible_notebooks_for_user

    notebook = visible_notebooks_for_user(user).filter(pk=pk).first()

    if not notebook:
        raise ValidationError("That Jupyter notebook is not available.")

    return notebook


def parse_parameters(raw):
    """``{"name": "value"}`` from a dict or from text with one ``name=value`` per line."""
    if raw in (None, ""):
        return {}

    if isinstance(raw, str):
        pairs = []

        for line in raw.splitlines():
            if line.strip():
                key, sep, value = line.partition("=")

                if not sep:
                    raise ValidationError(f"Parameter line needs name=value: {line.strip()[:40]}")

                pairs.append((key.strip(), value.strip()))
    elif isinstance(raw, dict):
        pairs = [(str(k).strip(), str(v).strip()) for k, v in raw.items()]
    else:
        raise ValidationError("Invalid parameters.")

    if len(pairs) > MAX_PARAMS:
        raise ValidationError(f"At most {MAX_PARAMS} parameters.")

    result = {}

    for key, value in pairs:
        if not PARAM_KEY.match(key):
            raise ValidationError(f"Invalid parameter name: {key[:40]}")
        if len(value) > 200:
            raise ValidationError(f"Parameter {key} is too long.")

        result[key] = value

    return result


def apply_step_fields(step, user, data):
    """Copy the editable fields present in ``data`` onto ``step`` (not saved)."""
    if "title" in data:
        step.title = _text(data["title"], "title", required=True)
    if "notes" in data:
        step.notes = _text(data["notes"], "notes")
    if "kind" in data:
        step.kind = _choice(data["kind"], WorkflowStep.Kind.choices, "kind")
    if "status" in data:
        status = _choice(data["status"], WorkflowStep.Status.choices, "status")

        if status == "done" and step.status != "done":
            step.finished_at = timezone.now()
        elif status != "done":
            step.finished_at = None

        step.status = status
    if "due_date" in data:
        step.due_date = _parse_deadline(data["due_date"])
    if "assignee" in data:
        raw = data["assignee"]
        step.assignee = get_user_model().objects.filter(pk=raw, is_active=True).first() if raw else None
    if "entry" in data:
        step.entry = _link(data["entry"], _entry_for, user)
    if "molecule" in data:
        step.molecule = _link(data["molecule"], _molecule_for, user)
    if "sample" in data:
        step.sample = _link(data["sample"], _sample_for, user)
    if any(k in data for k in ("jupyter_notebook", "parameters", "result_note")):
        config = dict(step.config or {})

        if "jupyter_notebook" in data:
            raw = data["jupyter_notebook"]

            if raw in (None, "", 0):
                config.pop("notebook_id", None)
            else:
                try:
                    config["notebook_id"] = _notebook_for(user, int(raw)).pk
                except (TypeError, ValueError):
                    raise ValidationError("Invalid notebook.")
        if "parameters" in data:
            config["parameters"] = parse_parameters(data["parameters"])
        if "result_note" in data:
            config["result_note"] = _text(data["result_note"], "result_note")

        step.config = config
    if "x" in data:
        step.x = int(data["x"])
    if "y" in data:
        step.y = int(data["y"])


def sync_notebook_step(step, user):
    """Keep a linked ELN step in step with this one (done <-> finished)."""
    nb = step.notebook_step

    if not nb:
        return

    finished = step.status == "done"

    if nb.finished != finished:
        nb.finished = finished
        nb.finished_at = timezone.now() if finished else None
        nb.finished_by = user if finished else None
        nb.save(update_fields=["finished", "finished_at", "finished_by"])


def add_step(workflow, user, data):
    if workflow.steps.count() >= MAX_STEPS:
        raise ValidationError(f"At most {MAX_STEPS} steps per workflow.")

    step = WorkflowStep(workflow=workflow)

    apply_step_fields(step, user, {"title": "New step", **data})
    step.save()
    sync_notebook_step(step, user)

    return step


def update_step(step, user, data):
    apply_step_fields(step, user, data)
    step.save()
    sync_notebook_step(step, user)

    return step


def _would_cycle(workflow, source_id, target_id):
    """True when adding source -> target would close a loop."""
    children = {}

    for src, tgt in workflow.edges.values_list("source_id", "target_id"):
        children.setdefault(src, []).append(tgt)

    stack, seen = [target_id], set()

    while stack:
        node = stack.pop()

        if node == source_id:
            return True
        if node in seen:
            continue

        seen.add(node)
        stack.extend(children.get(node, []))

    return False


def add_edge(workflow, source_id, target_id):
    steps = {s.pk: s for s in workflow.steps.filter(pk__in=[source_id, target_id])}

    if source_id == target_id or len(steps) != 2:
        raise ValidationError("Connect two different steps of this workflow.")
    if _would_cycle(workflow, source_id, target_id):
        raise ValidationError("That connection would create a loop.")

    edge, _ = WorkflowEdge.objects.get_or_create(
        workflow=workflow, source=steps[source_id], target=steps[target_id]
    )

    return edge


def import_eln_steps(workflow, user, entry_id):
    """Turn the steps of an ELN entry into linked workflow steps, chained in order."""
    entry = _entry_for(user, entry_id)
    existing = set(workflow.steps.exclude(notebook_step=None).values_list("notebook_step_id", flat=True))
    created, previous = [], None
    base_y = (workflow.steps.order_by("-y").values_list("y", flat=True).first() or 0) + 120

    for index, nb in enumerate(entry.steps.all()):
        if nb.pk in existing:
            continue
        if workflow.steps.count() + len(created) >= MAX_STEPS:
            break

        step = WorkflowStep.objects.create(
            workflow=workflow,
            title=nb.body[:200],
            entry=entry,
            notebook_step=nb,
            status="done" if nb.finished else "todo",
            finished_at=nb.finished_at,
            due_date=nb.deadline,
            x=40 + (index % 4) * 240,
            y=base_y + (index // 4) * 120,
        )

        if previous:
            WorkflowEdge.objects.get_or_create(workflow=workflow, source=previous, target=step)

        previous = step
        created.append(step)

    return created


# --- serialisation -----------------------------------------------------------


def _url(name, pk):
    try:
        return reverse(name, args=[pk])
    except NoReverseMatch:
        return ""


def _jupyter_info(step):
    config = step.config or {}
    notebook_id = config.get("notebook_id")
    label = url = ""

    if notebook_id:
        from core.models.lab_tools.notebook import JupyterNotebook

        notebook = JupyterNotebook.objects.filter(pk=notebook_id).first()

        label = notebook.title if notebook else "(removed notebook)"
        url = _url("jupyter_workspace", notebook_id) if notebook else ""

    return {
        "jupyter_notebook": notebook_id,
        "jupyter_label": label,
        "jupyter_url": url,
        "parameters": "\n".join(f"{k}={v}" for k, v in (config.get("parameters") or {}).items()),
        "result_note": config.get("result_note", ""),
    }


def _latest_run(step):
    from core.services.workflow_runs import serialize_run

    run = step.runs.select_related("started_by").first() if step.kind == "jupyter" else None

    return {"run": serialize_run(run) if run else None}


def serialize_step(step):
    return {
        **_jupyter_info(step),
        **_latest_run(step),
        "id": step.pk,
        "title": step.title,
        "notes": step.notes,
        "kind": step.kind,
        "status": step.status,
        "assignee": step.assignee_id,
        "assignee_name": step.assignee.get_username() if step.assignee else "",
        "due_date": timezone.localtime(step.due_date).strftime("%Y-%m-%dT%H:%M") if step.due_date else "",
        "x": step.x,
        "y": step.y,
        "entry": step.entry_id,
        "entry_label": step.entry.title if step.entry else "",
        "entry_url": _url("notebook_entry", step.entry_id) if step.entry_id else "",
        "molecule": step.molecule_id,
        "molecule_label": step.molecule.name if step.molecule else "",
        "molecule_url": _url("molecular_sequence_detail", step.molecule_id) if step.molecule_id else "",
        "sample": step.sample_id,
        "sample_label": step.sample.sample_id if step.sample else "",
        "sample_url": _url("sample_detail", step.sample_id) if step.sample_id else "",
        "from_eln": bool(step.notebook_step_id),
    }


def serialize(workflow):
    steps = workflow.steps.select_related("assignee", "entry", "molecule", "sample")
    items = [serialize_step(s) for s in steps]
    counts = {"todo": 0, "doing": 0, "done": 0, "blocked": 0}

    for item in items:
        counts[item["status"]] += 1

    return {
        "id": workflow.pk,
        "name": workflow.name,
        "description": workflow.description,
        "status": workflow.status,
        "owner": workflow.owner.get_username(),
        "entry": workflow.entry_id,
        "entry_label": workflow.entry.title if workflow.entry else "",
        "members": [{"id": u.pk, "name": u.get_username()} for u in workflow.members.all()],
        "steps": items,
        "edges": [{"id": e.pk, "source": e.source_id, "target": e.target_id} for e in workflow.edges.all()],
        "counts": counts,
    }


def update_workflow(workflow, user, data):
    if "name" in data:
        workflow.name = _text(data["name"], "name", required=True)
    if "description" in data:
        workflow.description = _text(data["description"], "description")
    if "status" in data:
        workflow.status = _choice(data["status"], Workflow.Status.choices, "status")
    if "entry" in data:
        workflow.entry = _link(data["entry"], _entry_for, user)

    workflow.save()

    if "members" in data and (user.is_superuser or workflow.owner_id == user.pk):
        ids = [int(x) for x in data["members"] if str(x).isdigit()]

        workflow.members.set(get_user_model().objects.filter(pk__in=ids, is_active=True).exclude(pk=workflow.owner_id))

    return workflow
