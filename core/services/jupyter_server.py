"""Official Jupyter Notebook servers hosted in Slurm allocations."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from core.models.lab_tools.notebook import (
    JupyterKernelSession,
    JupyterNotebook,
)
from core.services.jupyter_notebooks import (
    JupyterNotebookError,
    normalize_notebook,
)


ACTIVE_STATUSES = {
    "submitted",
    "pending",
    "running",
}

TERMINAL_STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "timeout",
}

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SAFE_USERNAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SAFE_BASE_URL_RE = re.compile(
    r"^/biobank/internal/lab-tools/jupyter/node/[A-Za-z0-9_.-]+/[0-9]{1,5}/$"
)


def server_runner():
    return Path(
        getattr(
            settings,
            "BIOBANK_JUPYTER_SERVER_RUNNER",
            "/usr/local/sbin/biobank-jupyter-server-runner",
        )
    )


def storage_root():
    return Path(
        getattr(
            settings,
            "BIOBANK_JUPYTER_STORAGE_ROOT",
            "/home/public/biobank/notebooks/users",
        )
    )


def server_job_root():
    return Path(
        getattr(
            settings,
            "BIOBANK_JUPYTER_SERVER_JOB_ROOT",
            "/home/public/biobank/jobs",
        )
    )


def _safe_username(value):
    username = SAFE_USERNAME_RE.sub(
        "_",
        str(value or "").strip(),
    ).strip("._-")

    if not username:
        raise JupyterNotebookError(
            "The application username is invalid."
        )

    return username[:100]


def _ensure_child(root, candidate):
    root = Path(root).resolve()
    candidate = Path(candidate).resolve()

    if candidate == root or root not in candidate.parents:
        raise JupyterNotebookError(
            "The Jupyter path is outside its protected root."
        )

    return candidate


def workspace_for_notebook(notebook):
    if notebook.owner_id is None:
        raise JupyterNotebookError(
            "The notebook does not have an owner."
        )

    username = _safe_username(
        notebook.owner.get_username()
    )

    return _ensure_child(
        storage_root(),
        storage_root()
        / f"user_{notebook.owner_id}_{username}"
        / f"notebook_{notebook.id}",
    )


def notebook_file_for_notebook(notebook):
    return workspace_for_notebook(notebook) / "notebook.ipynb"


def starter_notebook(title, username):
    return {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3 (ipykernel)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
            },
            "biobank": {
                "title": str(title or "").strip(),
                "owner": str(username or "").strip(),
                "official_jupyter_server": True,
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def can_view_notebook(user, notebook):
    if not user.is_authenticated:
        return False

    return bool(
        user.is_superuser
        or notebook.owner_id == user.id
    )


def can_edit_notebook(user, notebook):
    return can_view_notebook(user, notebook)


def visible_notebooks_for_user(user):
    notebooks = JupyterNotebook.objects.filter(
        is_archived=False
    )

    if user.is_superuser:
        return notebooks

    return notebooks.filter(owner=user)


def _runner_command(*arguments):
    runner = server_runner()

    if not runner.is_absolute():
        raise JupyterNotebookError(
            "The Jupyter server runner path must be absolute."
        )

    return [
        "sudo",
        "-n",
        "-u",
        "biobank",
        str(runner),
        *[str(argument) for argument in arguments],
    ]


def _parse_runner_output(output):
    output = str(output or "").strip()

    for line in reversed(output.splitlines()):
        line = line.strip()

        if not line.startswith("{"):
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            return payload

    raise JupyterNotebookError(
        "The Jupyter server runner returned invalid output."
    )


def _run_server_runner(*arguments, timeout=30):
    try:
        completed = subprocess.run(
            _runner_command(*arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise JupyterNotebookError(
            "The Jupyter server runner timed out."
        ) from exc
    except OSError as exc:
        raise JupyterNotebookError(
            "The Jupyter server runner could not be started."
        ) from exc

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Unknown runner error."
        )

        raise JupyterNotebookError(
            f"Jupyter server runner failed: {message}"
        )

    return _parse_runner_output(completed.stdout)


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
            "CPU, memory and duration must be integers."
        ) from exc

    allowed_partitions = tuple(
        getattr(
            settings,
            "BIOBANK_JUPYTER_PARTITIONS",
            ("basic", "max50"),
        )
    )

    if str(partition) not in allowed_partitions:
        raise JupyterNotebookError(
            "Invalid Slurm partition."
        )

    if not 1 <= cpus <= 128:
        raise JupyterNotebookError(
            "CPU cores must be between 1 and 128."
        )

    if not 1024 <= memory_mb <= 1048576:
        raise JupyterNotebookError(
            "Memory must be between 1024 and "
            "1048576 MB."
        )

    if not 5 <= time_minutes <= 10080:
        raise JupyterNotebookError(
            "Session duration must be between "
            "5 minutes and 7 days."
        )

    return {
        "cpus": cpus,
        "memory_mb": memory_mb,
        "time_minutes": time_minutes,
        "partition": str(partition),
    }


def _mapped_status(state, ready=False):
    state = str(state or "").upper()

    if state in {
        "PENDING",
        "CONFIGURING",
        "RESV_DEL_HOLD",
        "REQUEUE_HOLD",
    }:
        return "pending"

    if state in {
        "RUNNING",
        "COMPLETING",
    }:
        return "running" if ready else "pending"

    if state == "COMPLETED":
        return "completed"

    if state in {
        "CANCELLED",
        "PREEMPTED",
    }:
        return "cancelled"

    if state == "TIMEOUT":
        return "timeout"

    if state in {
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "BOOT_FAIL",
        "DEADLINE",
    }:
        return "failed"

    return "unknown"


def _safe_server_metadata(payload):
    server = payload.get("server")

    if not isinstance(server, dict):
        return {}

    return {
        key: server[key]
        for key in (
            "status",
            "host",
            "port",
            "base_url",
            "default_url",
            "notebook",
            "ready_at",
        )
        if key in server
    }


def _write_initial_document(notebook, notebook_file):
    notebook_file = _ensure_child(
        storage_root(),
        notebook_file,
    )

    if not notebook_file.is_file():
        raise JupyterNotebookError(
            "The runner did not create the notebook file."
        )

    document = normalize_notebook(
        notebook.notebook_json
        or starter_notebook(
            notebook.title,
            (
                notebook.owner.get_username()
                if notebook.owner
                else ""
            ),
        )
    )

    notebook_file.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )

    return document


def sync_notebook_from_disk(notebook):
    notebook_file = notebook_file_for_notebook(
        notebook
    )

    if not notebook_file.is_file():
        return normalize_notebook(
            notebook.notebook_json
        )

    try:
        document = normalize_notebook(
            json.loads(
                notebook_file.read_text()
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise JupyterNotebookError(
            "The saved notebook file is invalid."
        ) from exc

    if document != notebook.notebook_json:
        notebook.notebook_json = document
        notebook.save(
            update_fields=[
                "notebook_json",
                "updated_at",
            ]
        )

    return document


def load_notebook_document(notebook):
    return sync_notebook_from_disk(notebook)


def active_session_for_notebook(notebook):
    session = (
        notebook.sessions
        .filter(status__in=ACTIVE_STATUSES)
        .select_related(
            "notebook",
            "notebook__owner",
            "started_by",
        )
        .first()
    )

    if session is None:
        return None

    session = refresh_session(session)

    if session.status in ACTIVE_STATUSES:
        return session

    return None


def start_session(
    notebook,
    user,
    *,
    cpus,
    memory_mb,
    time_minutes,
    partition,
):
    if not can_edit_notebook(user, notebook):
        raise JupyterNotebookError(
            "Permission denied."
        )

    existing = active_session_for_notebook(
        notebook
    )

    if existing is not None:
        return existing

    resources = _validate_resources(
        cpus=cpus,
        memory_mb=memory_mb,
        time_minutes=time_minutes,
        partition=partition,
    )

    response = _run_server_runner(
        "server-start",
        notebook.id,
        user.id,
        user.get_username(),
        resources["cpus"],
        resources["memory_mb"],
        resources["time_minutes"],
        resources["partition"],
    )

    run_id = str(
        response.get("run_id") or ""
    )
    job_id = str(
        response.get("job_id") or ""
    )
    run_directory = str(
        response.get("run_dir") or ""
    )

    if not RUN_ID_RE.fullmatch(run_id):
        raise JupyterNotebookError(
            "The runner returned an invalid run identifier."
        )

    if not job_id.isdigit():
        raise JupyterNotebookError(
            "The runner returned an invalid Slurm job ID."
        )

    notebook_file = _ensure_child(
        storage_root(),
        response.get("notebook_file")
        or notebook_file_for_notebook(notebook),
    )

    expected_file = notebook_file_for_notebook(
        notebook
    ).resolve()

    if notebook_file != expected_file:
        try:
            _run_server_runner(
                "server-stop",
                notebook.id,
                run_id,
            )
        except JupyterNotebookError:
            pass

        raise JupyterNotebookError(
            "The runner returned an unexpected notebook path."
        )

    try:
        document = _write_initial_document(
            notebook,
            notebook_file,
        )

        session = JupyterKernelSession.objects.create(
            notebook=notebook,
            started_by=user,
            job_id=job_id,
            run_id=run_id,
            status="submitted",
            partition=resources["partition"],
            cpus=resources["cpus"],
            memory_mb=resources["memory_mb"],
            time_minutes=resources["time_minutes"],
            run_directory=run_directory,
            kernel_info={
                "official_server": True,
                "workspace": str(
                    workspace_for_notebook(notebook)
                ),
                "notebook_file": str(notebook_file),
            },
            expires_at=(
                timezone.now()
                + timedelta(
                    minutes=resources["time_minutes"]
                )
            ),
        )

        if document != notebook.notebook_json:
            notebook.notebook_json = document
            notebook.updated_by = user
            notebook.save(
                update_fields=[
                    "notebook_json",
                    "updated_by",
                    "updated_at",
                ]
            )

        return session
    except Exception:
        try:
            _run_server_runner(
                "server-stop",
                notebook.id,
                run_id,
            )
        except JupyterNotebookError:
            pass

        raise


def refresh_session(session):
    if session.status not in ACTIVE_STATUSES:
        return session

    payload = _run_server_runner(
        "server-status",
        session.notebook_id,
        session.run_id,
    )

    ready = bool(payload.get("ready"))
    state = str(payload.get("state") or "")
    status = _mapped_status(
        state,
        ready=ready,
    )
    now = timezone.now()

    kernel_info = dict(
        session.kernel_info or {}
    )
    kernel_info.update(
        {
            "official_server": True,
            "slurm_state": state,
            "server": _safe_server_metadata(
                payload
            ),
        }
    )

    session.status = status
    session.kernel_info = kernel_info
    session.last_error = str(
        payload.get("error") or ""
    )

    update_fields = [
        "status",
        "kernel_info",
        "last_error",
        "updated_at",
    ]

    if state.upper() in {
        "RUNNING",
        "COMPLETING",
    } and session.started_at is None:
        session.started_at = now
        update_fields.append("started_at")

    if ready and session.ready_at is None:
        session.ready_at = now
        update_fields.append("ready_at")

    if status in TERMINAL_STATUSES:
        session.finished_at = (
            session.finished_at or now
        )
        update_fields.append("finished_at")

        try:
            sync_notebook_from_disk(
                session.notebook
            )
        except JupyterNotebookError as exc:
            session.last_error = str(exc)

    session.save(
        update_fields=list(
            dict.fromkeys(update_fields)
        )
    )

    return session


def stop_session(session, user):
    if not can_edit_notebook(
        user,
        session.notebook,
    ):
        raise JupyterNotebookError(
            "Permission denied."
        )

    try:
        sync_notebook_from_disk(
            session.notebook
        )
    except JupyterNotebookError:
        pass

    _run_server_runner(
        "server-stop",
        session.notebook_id,
        session.run_id,
    )

    session.status = "cancelled"
    session.finished_at = (
        session.finished_at or timezone.now()
    )
    session.save(
        update_fields=[
            "status",
            "finished_at",
            "updated_at",
        ]
    )

    try:
        sync_notebook_from_disk(
            session.notebook
        )
    except JupyterNotebookError:
        pass

    return session


def connection_redirect_path(session):
    session = refresh_session(session)

    if session.status != "running":
        raise JupyterNotebookError(
            "The Jupyter server is not ready."
        )

    connection_file = _ensure_child(
        server_job_root(),
        Path(session.run_directory)
        / "connection.json",
    )

    try:
        connection = json.loads(
            connection_file.read_text()
        )
    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise JupyterNotebookError(
            "The protected Jupyter connection is unavailable."
        ) from exc

    host = str(connection.get("host") or "")
    port = connection.get("port")
    base_url = str(
        connection.get("base_url") or ""
    )
    token = str(connection.get("token") or "")
    default_url = str(
        connection.get("default_url")
        or "/tree/notebook.ipynb"
    )

    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise JupyterNotebookError(
            "The protected connection port is invalid."
        ) from exc

    expected_base = f"/biobank/internal/lab-tools/jupyter/node/{host}/{port}/"

    if (
        not host
        or not 1 <= port <= 65535
        or base_url != expected_base
        or not SAFE_BASE_URL_RE.fullmatch(base_url)
        or not token
        or not default_url.startswith("/")
        or default_url.startswith("//")
    ):
        raise JupyterNotebookError(
            "The protected Jupyter connection is invalid."
        )

    safe_server = (
        session.kernel_info
        .get("server", {})
        if isinstance(
            session.kernel_info,
            dict,
        )
        else {}
    )

    if safe_server:
        if (
            str(safe_server.get("host")) != host
            or int(safe_server.get("port")) != port
            or str(
                safe_server.get("base_url")
            ) != base_url
        ):
            raise JupyterNotebookError(
                "The Jupyter connection metadata does not match."
            )

    return (
        f"{base_url.rstrip('/')}"
        f"{default_url}"
        f"?token={quote(token, safe='')}"
    )


def delete_notebook_workspace(notebook):
    workspace = workspace_for_notebook(
        notebook
    )

    if not workspace.exists():
        return False

    _ensure_child(
        storage_root(),
        workspace,
    )

    shutil.rmtree(workspace)
    return True
