"""Persistence and controlled Slurm execution for ELN Jupyter notebooks."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models.lab_tools.notebook import (
    NotebookKernelDocument,
    NotebookKernelExecution,
    default_jupyter_notebook,
)


class JupyterNotebookError(ValueError):
    """Raised when a notebook or managed execution is invalid."""


MAX_NOTEBOOK_BYTES = 4 * 1024 * 1024
MAX_RESULT_BYTES = 32 * 1024 * 1024
MAX_CELLS = 200
MAX_CELL_SOURCE_BYTES = 1024 * 1024
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def notebook_root() -> Path:
    return Path(
        getattr(
            settings,
            "BIOBANK_JUPYTER_NOTEBOOK_ROOT",
            "/home/public/biobank/notebooks",
        )
    ).resolve()


def job_root() -> Path:
    return Path(
        getattr(
            settings,
            "BIOBANK_JUPYTER_JOB_ROOT",
            "/home/public/biobank/jobs",
        )
    ).resolve()


def _source_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "".join(value)
    raise JupyterNotebookError("Cell source must be text or a list of text lines.")


def _normalized_output(output):
    if not isinstance(output, dict):
        return None

    output_type = output.get("output_type")
    if output_type == "stream":
        return {
            "name": str(output.get("name") or "stdout")[:16],
            "output_type": "stream",
            "text": _source_text(output.get("text", ""))[:MAX_CELL_SOURCE_BYTES],
        }

    if output_type == "error":
        traceback = output.get("traceback", [])
        if not isinstance(traceback, list):
            traceback = []
        return {
            "ename": str(output.get("ename") or "Error")[:255],
            "evalue": str(output.get("evalue") or "")[:4096],
            "output_type": "error",
            "traceback": [str(line)[:4096] for line in traceback[:100]],
        }

    if output_type in {"display_data", "execute_result"}:
        data = output.get("data", {})
        if not isinstance(data, dict):
            data = {}

        allowed_data = {}
        for mime_type in ("text/plain", "image/png", "image/jpeg"):
            if mime_type not in data:
                continue
            value = data[mime_type]
            if isinstance(value, list):
                value = "".join(str(part) for part in value)
            if isinstance(value, str):
                allowed_data[mime_type] = value[: 8 * 1024 * 1024]

        normalized = {
            "data": allowed_data,
            "metadata": {},
            "output_type": output_type,
        }
        if output_type == "execute_result":
            normalized["execution_count"] = output.get("execution_count")
        return normalized

    return None


def normalize_notebook(payload) -> dict:
    """Validate and return a bounded Jupyter notebook v4 document."""
    if not isinstance(payload, dict):
        raise JupyterNotebookError("Notebook payload must be an object.")

    cells = payload.get("cells", [])
    if not isinstance(cells, list):
        raise JupyterNotebookError("Notebook cells must be a list.")
    if len(cells) > MAX_CELLS:
        raise JupyterNotebookError(f"Notebook may contain at most {MAX_CELLS} cells.")

    normalized_cells = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise JupyterNotebookError(f"Cell {index + 1} must be an object.")

        cell_type = cell.get("cell_type")
        if cell_type not in {"code", "markdown", "raw"}:
            raise JupyterNotebookError(f"Unsupported cell type at cell {index + 1}.")

        source = _source_text(cell.get("source", ""))
        if len(source.encode("utf-8")) > MAX_CELL_SOURCE_BYTES:
            raise JupyterNotebookError(f"Cell {index + 1} is too large.")

        cell_id = str(cell.get("id") or uuid.uuid4().hex[:12])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cell_id):
            cell_id = uuid.uuid4().hex[:12]

        normalized = {
            "cell_type": cell_type,
            "id": cell_id,
            "metadata": {},
            "source": source,
        }

        if cell_type == "code":
            outputs = cell.get("outputs", [])
            if not isinstance(outputs, list):
                outputs = []
            normalized["execution_count"] = cell.get("execution_count")
            normalized["outputs"] = [
                clean
                for clean in (_normalized_output(item) for item in outputs[:100])
                if clean is not None
            ]

        normalized_cells.append(normalized)

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    kernelspec = metadata.get("kernelspec", {})
    if not isinstance(kernelspec, dict):
        kernelspec = {}

    language_info = metadata.get("language_info", {})
    if not isinstance(language_info, dict):
        language_info = {}

    normalized_notebook = {
        "cells": normalized_cells,
        "metadata": {
            "kernelspec": {
                "display_name": str(kernelspec.get("display_name") or "Python 3")[:255],
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": str(language_info.get("name") or "python")[:64],
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    encoded = json.dumps(normalized_notebook).encode("utf-8")
    if len(encoded) > MAX_NOTEBOOK_BYTES:
        raise JupyterNotebookError("Notebook is too large.")

    return normalized_notebook


def get_or_create_document(entry, user=None) -> NotebookKernelDocument:
    document, created = NotebookKernelDocument.objects.get_or_create(
        entry=entry,
        defaults={
            "title": f"{entry.title} analysis",
            "notebook_json": default_jupyter_notebook(),
            "created_by": user,
            "updated_by": user,
        },
    )
    if created:
        persist_document(document)
    return document


def document_path(document: NotebookKernelDocument, *, suffix="") -> Path:
    directory = notebook_root() / f"entry_{document.entry_id}"
    filename = f"document_{document.pk}{suffix}.ipynb"
    return directory / filename


def _ensure_child(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root = root.resolve()
    if resolved != root and root not in resolved.parents:
        raise JupyterNotebookError("Managed path is outside its configured root.")
    return resolved


def _atomic_json_write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o2770)
    _ensure_child(path, notebook_root())
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, ensure_ascii=False)
            handle.write("\n")
        os.chmod(temporary_name, 0o660)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return path


def persist_document(document: NotebookKernelDocument) -> Path:
    document.notebook_json = normalize_notebook(document.notebook_json)
    return _atomic_json_write(document_path(document), document.notebook_json)


def _runner_command(*arguments):
    return [
        str(getattr(settings, "BIOBANK_JUPYTER_SUDO", "/usr/bin/sudo")),
        "--non-interactive",
        "--user=biobank",
        "--",
        str(
            getattr(
                settings,
                "BIOBANK_JUPYTER_RUNNER",
                "/usr/local/sbin/biobank-notebook-runner",
            )
        ),
        *[str(value) for value in arguments],
    ]


def _run_runner(*arguments) -> dict:
    try:
        completed = subprocess.run(
            _runner_command(*arguments),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        message = getattr(exc, "stderr", "") or str(exc)
        raise JupyterNotebookError(f"Notebook runner failed: {message.strip()}") from exc

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise JupyterNotebookError("Notebook runner returned invalid data.") from exc


def submit_document(
    document: NotebookKernelDocument,
    user,
    *,
    cpus=2,
    memory_mb=8192,
    time_minutes=60,
    partition=None,
    cell_index=None,
) -> NotebookKernelExecution:
    cpus = int(cpus)
    memory_mb = int(memory_mb)
    time_minutes = int(time_minutes)
    partition = str(
        partition or settings.BIOBANK_JUPYTER_PARTITION
    ).strip()

    allowed_partitions = set(
        settings.BIOBANK_JUPYTER_PARTITIONS
    )
    if partition not in allowed_partitions:
        raise JupyterNotebookError(
            "Invalid Slurm partition."
        )

    if not 1 <= cpus <= 8:
        raise JupyterNotebookError("CPU count must be between 1 and 8.")
    if not 1024 <= memory_mb <= 32768:
        raise JupyterNotebookError("Memory must be between 1024 and 32768 MB.")
    if not 1 <= time_minutes <= 240:
        raise JupyterNotebookError("Time must be between 1 and 240 minutes.")

    notebook = normalize_notebook(document.notebook_json)
    if cell_index is not None:
        cell_index = int(cell_index)
        if not 0 <= cell_index < len(notebook["cells"]):
            raise JupyterNotebookError("Requested cell does not exist.")
        notebook = copy.deepcopy(notebook)
        notebook["cells"] = notebook["cells"][: cell_index + 1]

    source_path = document_path(
        document,
        suffix=f"_execution_{uuid.uuid4().hex}",
    )
    _atomic_json_write(source_path, notebook)

    payload = _run_runner(
        "submit",
        document.entry_id,
        user.get_username(),
        source_path,
        cpus,
        memory_mb,
        time_minutes,
        partition,
    )

    run_id = str(payload.get("run_id") or "")
    run_directory = _ensure_child(
        Path(payload.get("run_dir") or ""),
        job_root(),
    )
    job_id = str(payload.get("job_id") or "")

    if not RUN_ID_RE.fullmatch(run_id) or not job_id.isdigit():
        raise JupyterNotebookError("Notebook runner returned an invalid job identity.")

    return NotebookKernelExecution.objects.create(
        document=document,
        submitted_by=user,
        job_id=job_id,
        run_id=run_id,
        status="submitted",
        requested_cell_index=cell_index,
        cpus=cpus,
        memory_mb=memory_mb,
        time_minutes=time_minutes,
        partition=partition,
        source_path=str(source_path),
        run_directory=str(run_directory),
        result_path=str(run_directory / "executed.ipynb"),
    )


def _mapped_status(slurm_state: str) -> str:
    state = str(slurm_state or "").upper().split()[0].rstrip("+")
    if state in {"PENDING", "CONFIGURING", "REQUEUED", "RESIZING"}:
        return "pending"
    if state in {"RUNNING", "COMPLETING", "STAGE_OUT", "SUSPENDED"}:
        return "running"
    if state == "COMPLETED":
        return "completed"
    if state in {"CANCELLED", "PREEMPTED"}:
        return "cancelled"
    if state in {
        "FAILED",
        "TIMEOUT",
        "OUT_OF_MEMORY",
        "NODE_FAIL",
        "BOOT_FAIL",
        "DEADLINE",
        "REVOKED",
    }:
        return "failed"
    return "unknown"


def _load_managed_json(path: Path, root: Path, maximum: int) -> dict:
    path = _ensure_child(path, root)
    if not path.is_file():
        raise JupyterNotebookError("Managed result file was not found.")
    if path.stat().st_size > maximum:
        raise JupyterNotebookError("Managed result file is too large.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JupyterNotebookError("Managed result file is invalid.") from exc


def _merge_execution_result(document, executed, cell_index):
    executed = normalize_notebook(executed)
    if cell_index is None:
        return executed

    current = normalize_notebook(document.notebook_json)
    executed_by_id = {cell.get("id"): cell for cell in executed["cells"]}
    for cell in current["cells"]:
        result_cell = executed_by_id.get(cell.get("id"))
        if cell.get("cell_type") != "code" or not result_cell:
            continue
        cell["outputs"] = result_cell.get("outputs", [])
        cell["execution_count"] = result_cell.get("execution_count")
    return current


def refresh_execution(execution: NotebookKernelExecution) -> NotebookKernelExecution:
    payload = _run_runner(
        "status",
        execution.document.entry_id,
        execution.run_id,
    )
    previous_status = execution.status
    execution.status = _mapped_status(payload.get("state"))

    summary_path = Path(execution.run_directory) / "execution.json"
    if payload.get("summary_available") and summary_path.is_file():
        execution.summary_json = _load_managed_json(
            summary_path,
            job_root(),
            MAX_NOTEBOOK_BYTES,
        )
        started = parse_datetime(execution.summary_json.get("started_at") or "")
        finished = parse_datetime(execution.summary_json.get("finished_at") or "")
        execution.started_at = started or execution.started_at
        execution.finished_at = finished or execution.finished_at

    if execution.status == "completed" and payload.get("result_available"):
        result = _load_managed_json(
            Path(execution.result_path),
            job_root(),
            MAX_RESULT_BYTES,
        )
        document = execution.document
        document.notebook_json = _merge_execution_result(
            document,
            result,
            execution.requested_cell_index,
        )
        document.updated_by = execution.submitted_by
        document.save(update_fields=["notebook_json", "updated_by", "updated_at"])
        persist_document(document)

    if execution.status in {"completed", "failed", "cancelled"} and not execution.finished_at:
        execution.finished_at = timezone.now()

    fields = [
        "status",
        "summary_json",
        "started_at",
        "finished_at",
        "updated_at",
    ]
    if execution.status != previous_status or execution.summary_json:
        execution.save(update_fields=fields)
    return execution


def cancel_execution(execution: NotebookKernelExecution) -> NotebookKernelExecution:
    _run_runner(
        "cancel",
        execution.document.entry_id,
        execution.run_id,
    )
    execution.status = "cancelled"
    execution.finished_at = timezone.now()
    execution.save(update_fields=["status", "finished_at", "updated_at"])
    return execution
