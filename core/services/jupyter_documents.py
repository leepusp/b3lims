"""Validation and normalization for persisted Jupyter documents."""

from __future__ import annotations

import json
import re
import uuid

class JupyterNotebookError(ValueError):
    """Raised when a notebook or managed execution is invalid."""

MAX_NOTEBOOK_BYTES = 4 * 1024 * 1024

MAX_CELLS = 200

MAX_CELL_SOURCE_BYTES = 1024 * 1024

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
