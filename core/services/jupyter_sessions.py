"""Persistent Slurm-backed Jupyter kernel sessions."""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models.lab_tools.notebook import (
    JupyterKernelSession,
    JupyterNotebook,
)
from core.services.jupyter_notebooks import (
    JupyterNotebookError,
    _ensure_child,
    _run_runner,
    job_root,
    normalize_notebook,
)


ACTIVE_STATUSES = {"submitted", "pending", "running"}

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def starter_notebook(title, username):
    """Return a valid, completely empty Jupyter notebook."""

    title = str(
        title or "Untitled Jupyter notebook"
    ).strip()
    username = str(username or "").strip()

    return {
        "cells": [],
        "metadata": {
            "biobank": {
                "title": title,
                "owner": username,
            },
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

def can_view_notebook(user, notebook):
    if not user or not user.is_authenticated or notebook is None:
        return False

    return bool(
        user.is_superuser
        or notebook.owner_id == user.id
    )


def can_edit_notebook(user, notebook):
    return can_view_notebook(user, notebook)


def visible_notebooks_for_user(user):
    queryset = JupyterNotebook.objects.filter(
        is_archived=False
    )

    if not user or not user.is_authenticated:
        return queryset.none()

    if user.is_superuser:
        return queryset

    return queryset.filter(owner=user)


def active_session_for_notebook(notebook):
    session = (
        notebook.sessions
        .filter(status__in=ACTIVE_STATUSES)
        .select_related("started_by")
        .first()
    )

    if session is None:
        return None

    session = refresh_session(session)

    if session.status in ACTIVE_STATUSES:
        return session

    return None


def _validate_resources(
    *,
    cpus,
    memory_mb,
    time_minutes,
    partition,
):
    try:
        cpus = int(cpus)
        memory_mb = int(memory_mb)
        time_minutes = int(time_minutes)
    except (TypeError, ValueError) as exc:
        raise JupyterNotebookError(
            "Invalid Jupyter resource selection."
        ) from exc

    partition = str(
        partition
        or getattr(
            settings,
            "BIOBANK_JUPYTER_PARTITION",
            "basic",
        )
    ).strip()

    allowed_partitions = set(
        getattr(
            settings,
            "BIOBANK_JUPYTER_PARTITIONS",
            ("basic", "max50"),
        )
    )

    if partition not in allowed_partitions:
        raise JupyterNotebookError(
            "Invalid Slurm partition."
        )
    if not 1 <= cpus <= 8:
        raise JupyterNotebookError(
            "CPU count must be between 1 and 8."
        )
    if not 1024 <= memory_mb <= 32768:
        raise JupyterNotebookError(
            "Memory must be between 1024 and 32768 MB."
        )
    if not 1 <= time_minutes <= 240:
        raise JupyterNotebookError(
            "Time must be between 1 and 240 minutes."
        )

    return cpus, memory_mb, time_minutes, partition


def _map_slurm_status(value):
    state = str(value or "UNKNOWN").upper()
    state = state.split("+", 1)[0]

    if state in {"CONFIGURING", "PENDING", "RESIZING"}:
        return "pending"

    if state in {"RUNNING", "COMPLETING", "SUSPENDED"}:
        return "running"

    if state == "COMPLETED":
        return "completed"

    if state in {"CANCELLED", "PREEMPTED"}:
        return "cancelled"

    if state in {
        "BOOT_FAIL",
        "DEADLINE",
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "REVOKED",
        "TIMEOUT",
    }:
        return "failed"

    return "unknown"


def start_session(
    notebook,
    user,
    *,
    cpus=2,
    memory_mb=8192,
    time_minutes=60,
    partition=None,
):
    if not can_edit_notebook(user, notebook):
        raise JupyterNotebookError(
            "You cannot start a session for this notebook."
        )

    resources = _validate_resources(
        cpus=cpus,
        memory_mb=memory_mb,
        time_minutes=time_minutes,
        partition=partition,
    )
    cpus, memory_mb, time_minutes, partition = resources

    with transaction.atomic():
        locked_notebook = (
            JupyterNotebook.objects
            .select_for_update()
            .get(pk=notebook.pk)
        )

        if active_session_for_notebook(locked_notebook):
            raise JupyterNotebookError(
                "This notebook already has an active Slurm session."
            )

        payload = _run_runner(
            "session-start",
            locked_notebook.id,
            user.get_username(),
            cpus,
            memory_mb,
            time_minutes,
            partition,
        )

        job_id = str(payload.get("job_id") or "")
        run_id = str(payload.get("run_id") or "")
        raw_run_directory = str(
            payload.get("run_dir") or ""
        )

        if not job_id.isdigit():
            raise JupyterNotebookError(
                "The runner returned an invalid Slurm job ID."
            )

        if not RUN_ID_RE.fullmatch(run_id):
            raise JupyterNotebookError(
                "The runner returned an invalid session ID."
            )

        if not raw_run_directory:
            raise JupyterNotebookError(
                "The runner did not return a session directory."
            )

        run_directory = _ensure_child(
            Path(raw_run_directory),
            job_root(),
        )

        return JupyterKernelSession.objects.create(
            notebook=locked_notebook,
            started_by=user,
            job_id=job_id,
            run_id=run_id,
            status="submitted",
            partition=partition,
            cpus=cpus,
            memory_mb=memory_mb,
            time_minutes=time_minutes,
            run_directory=str(run_directory),
        )


def refresh_session(session):
    payload = _run_runner(
        "session-status",
        session.notebook_id,
        session.run_id,
    )

    session.status = _map_slurm_status(
        payload.get("state")
    )

    fields = ["status", "updated_at"]
    now = timezone.now()

    kernel_info = (
        payload.get("kernel")
        or payload.get("kernel_info")
        or {}
    )

    if isinstance(kernel_info, dict) and kernel_info:
        session.kernel_info = kernel_info
        fields.append("kernel_info")

    if session.status == "running":
        if session.started_at is None:
            session.started_at = now
            fields.append("started_at")

        if session.ready_at is None:
            session.ready_at = now
            fields.append("ready_at")

        if session.expires_at is None:
            session.expires_at = now + timedelta(
                minutes=session.time_minutes
            )
            fields.append("expires_at")

    if session.status in {
        "completed",
        "failed",
        "cancelled",
    }:
        if session.finished_at is None:
            session.finished_at = now
            fields.append("finished_at")

    error = str(
        payload.get("error")
        or payload.get("message")
        or ""
    ).strip()

    if error and session.status == "failed":
        session.last_error = error
        fields.append("last_error")

    session.save(
        update_fields=list(dict.fromkeys(fields))
    )
    return session


def stop_session(session, user):
    if not can_edit_notebook(user, session.notebook):
        raise JupyterNotebookError(
            "You cannot stop this Jupyter session."
        )

    if session.status not in ACTIVE_STATUSES:
        return session

    _run_runner(
        "session-stop",
        session.notebook_id,
        session.run_id,
    )

    session.status = "cancelled"
    session.finished_at = timezone.now()
    session.save(
        update_fields=[
            "status",
            "finished_at",
            "updated_at",
        ]
    )

    return session


def _cell_source(cell):
    source = cell.get("source", "")

    if isinstance(source, list):
        return "".join(str(item) for item in source)

    return str(source or "")


def _session_file(session, filename):
    run_directory = Path(
        session.run_directory
    ).resolve()
    candidate = (
        run_directory / filename
    ).resolve()

    if run_directory not in candidate.parents:
        raise JupyterNotebookError(
            "Invalid Jupyter session path."
        )

    return candidate


def execute_cell(
    session,
    user,
    cell_index,
    *,
    execution_timeout=120,
):
    if not can_edit_notebook(user, session.notebook):
        raise JupyterNotebookError(
            "You cannot execute this notebook."
        )

    session = refresh_session(session)

    if session.status != "running":
        raise JupyterNotebookError(
            "The persistent Slurm session is not running."
        )

    notebook_data = normalize_notebook(
        copy.deepcopy(
            session.notebook.notebook_json
        )
    )

    try:
        cell_index = int(cell_index)
        cell = notebook_data["cells"][cell_index]
    except (TypeError, ValueError, IndexError) as exc:
        raise JupyterNotebookError(
            "Requested cell does not exist."
        ) from exc

    if cell.get("cell_type") != "code":
        raise JupyterNotebookError(
            "Only code cells can be executed."
        )

    request_id = uuid.uuid4().hex
    request_path = _session_file(
        session,
        f"cell-request-{request_id}.json",
    )
    response_path = _session_file(
        session,
        f"cell-response-{request_id}.json",
    )

    request_path.write_text(
        json.dumps(
            {
                "code": _cell_source(cell),
                "cell_index": cell_index,
            },
            ensure_ascii=False,
        )
    )

    try:
        payload = _run_runner(
            "session-execute",
            session.notebook_id,
            session.run_id,
            request_path,
            response_path,
            execution_timeout,
            timeout=execution_timeout + 30,
        )

        if response_path.is_file():
            result = json.loads(
                response_path.read_text()
            )
        else:
            result = payload.get("result") or payload
    finally:
        for temporary_path in (
            request_path,
            response_path,
        ):
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                # Response files are created by the Linux
                # service account. A cleanup ownership mismatch
                # must not turn a successful cell into a failure.
                pass

    if not isinstance(result, dict):
        raise JupyterNotebookError(
            "The kernel returned an invalid result."
        )

    outputs = result.get("outputs", [])
    if not isinstance(outputs, list):
        outputs = []

    cell["outputs"] = outputs
    cell["execution_count"] = result.get(
        "execution_count"
    )

    with transaction.atomic():
        locked_notebook = (
            JupyterNotebook.objects
            .select_for_update()
            .get(pk=session.notebook_id)
        )
        locked_notebook.notebook_json = notebook_data
        locked_notebook.updated_by = user
        locked_notebook.save(
            update_fields=[
                "notebook_json",
                "updated_by",
                "updated_at",
            ]
        )

        session.last_activity_at = timezone.now()
        session.save(
            update_fields=[
                "last_activity_at",
                "updated_at",
            ]
        )

    return result
