"""Independent tool records: create, open, save state, file and delete."""

import json
import logging
import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core.models.lab_tools.tool_record import ToolRecord

logger = logging.getLogger(__name__)

MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024

TOOL_HELP = {
    "gel": "Gel photo, lanes, marker calibration and band sizes.",
    "assembly": "Build a plasmid from parts, without an open vector.",
    "chemical": "Structure notes, SMILES/MOL, formula and mass.",
}
TOOL_FILE_TYPES = {
    "gel": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"},
    "assembly": {".gb", ".gbk", ".fa", ".fasta", ".txt", ".dna"},
    "chemical": {
        ".mol", ".sdf", ".smi", ".txt", ".cdxml", ".png", ".jpg",
        ".jpeg", ".svg",
    },
    "rnafold": {".fa", ".fasta", ".txt", ".gb", ".gbk", ".dbn", ".ct"},
    "protein3d": {
        ".pdb", ".ent", ".cif", ".mmcif", ".fa", ".fasta", ".txt",
    },
}
INLINE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def tool_choices():
    return ToolRecord.TOOL_CHOICES


def visible_tool_records(user):
    records = ToolRecord.objects.select_related("owner")

    return records if user.is_superuser else records.filter(owner=user)


def get_tool_record(record_id, user):
    record = visible_tool_records(user).filter(pk=record_id).first()

    if record is None:
        raise Http404("Tool record not found.")

    return record


def file_problem(tool, uploaded):
    """Return why an uploaded file does not fit this tool, or an empty string."""

    suffix = Path(uploaded.name or "").suffix.lower()

    if suffix not in TOOL_FILE_TYPES.get(tool, set()):
        return (
            "This tool does not accept that file type "
            f"({suffix or 'no extension'})."
        )

    if uploaded.size > MAX_FILE_BYTES:
        return "The file is larger than 25 MB."

    return ""


def _json_error(message, status=400):
    return JsonResponse({"status": "error", "message": message}, status=status)


@login_required
def tool_record_create(request):
    if request.method != "POST":
        return redirect("molecular_registry_index")

    tool = str(request.POST.get("tool") or "").strip()
    name = str(request.POST.get("name") or "").strip()[:255]

    if tool not in dict(ToolRecord.TOOL_CHOICES):
        messages.error(request, "Choose a valid tool type.")
        return redirect("molecular_registry_index")

    if not name:
        messages.error(request, "Name is required.")
        return redirect("molecular_registry_index")

    uploaded = request.FILES.get("file")

    if uploaded is not None:
        problem = file_problem(tool, uploaded)

        if problem:
            messages.error(request, problem)
            return redirect("molecular_registry_index")

    record = ToolRecord.objects.create(
        tool=tool,
        name=name,
        description=str(request.POST.get("description") or "").strip(),
        owner=request.user,
        data={},
    )

    if uploaded is not None:
        try:
            record.original_filename = Path(uploaded.name).name[:255]
            record.file.save(uploaded.name, uploaded, save=False)
            record.save(update_fields=["file", "original_filename", "updated_at"])
        except OSError as exc:
            logger.exception("Tool record file could not be stored")
            messages.error(
                request,
                f"The record was created, but its file could not be stored: {exc}",
            )

    return redirect("tool_record_detail", record_id=record.id)


@login_required
def tool_record_detail(request, record_id):
    record = get_tool_record(record_id, request.user)

    return render(
        request,
        "internal/lab_tools/tool_record_detail.html",
        {
            "record": record,
            "tool_label": record.get_tool_display(),
            "tool_choices": ToolRecord.CREATABLE_CHOICES,
            "has_file": bool(record.file and record.file.name),
        },
    )


@login_required
def tool_record_state_api(request, record_id):
    """Save the state of the windows (and optionally name/description)."""

    if request.method != "POST":
        return _json_error("POST is required.", 405)

    record = get_tool_record(record_id, request.user)

    if len(request.body) > MAX_STATE_BYTES:
        return _json_error("The state is too large.", 413)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return _json_error("The request is not valid JSON.")

    if not isinstance(payload, dict):
        return _json_error("The request must be a JSON object.")

    fields = ["updated_at"]

    if "data" in payload:
        if not isinstance(payload["data"], dict):
            return _json_error("data must be an object.")

        record.data = payload["data"]
        fields.append("data")

    if "name" in payload:
        name = str(payload["name"] or "").strip()[:255]

        if not name:
            return _json_error("Name is required.")

        record.name = name
        fields.append("name")

    if "description" in payload:
        record.description = str(payload["description"] or "")[:20000]
        fields.append("description")

    record.save(update_fields=fields)

    return JsonResponse(
        {
            "status": "success",
            "updated_at": record.updated_at.isoformat(),
        }
    )


@login_required
def tool_record_file_api(request, record_id):
    """GET the stored file; POST replaces it; DELETE-style removal via POST."""

    record = get_tool_record(record_id, request.user)

    if request.method == "GET":
        if not record.file or not record.file.name:
            raise Http404("This record has no file.")

        try:
            handle = record.file.open("rb")
        except OSError:
            raise Http404("The file is unavailable.")

        suffix = Path(record.original_filename or record.file.name).suffix.lower()
        inline = suffix in INLINE_TYPES
        response = FileResponse(
            handle,
            as_attachment=not inline,
            filename=record.original_filename or Path(record.file.name).name,
            content_type=(
                mimetypes.guess_type("x" + suffix)[0]
                or "application/octet-stream"
            ),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=0, must-revalidate"

        return response

    if request.method != "POST":
        return _json_error("GET or POST is required.", 405)

    if request.POST.get("remove") == "1":
        if record.file and record.file.name:
            record.file.delete(save=False)

        record.file = ""
        record.original_filename = ""
        record.save(update_fields=["file", "original_filename", "updated_at"])

        return JsonResponse({"status": "success", "has_file": False})

    uploaded = request.FILES.get("file")

    if uploaded is None:
        return _json_error("Choose a file.")

    problem = file_problem(record.tool, uploaded)

    if problem:
        return _json_error(problem, 413 if "25 MB" in problem else 400)

    old_name = record.file.name if record.file else ""

    try:
        with transaction.atomic():
            record.original_filename = Path(uploaded.name).name[:255]
            record.file.save(uploaded.name, uploaded, save=False)
            record.save(update_fields=["file", "original_filename", "updated_at"])
    except OSError as exc:
        logger.exception("Tool record file could not be stored")

        return _json_error(f"The file could not be stored: {exc}", 500)

    if old_name and old_name != record.file.name:
        record.file.storage.delete(old_name)

    return JsonResponse(
        {
            "status": "success",
            "has_file": True,
            "filename": record.original_filename,
        }
    )


@login_required
def tool_record_delete_api(request, record_id):
    if request.method != "POST":
        return _json_error("POST is required.", 405)

    record = get_tool_record(record_id, request.user)
    record.delete()

    return JsonResponse(
        {
            "status": "success",
            "redirect_url": reverse("molecular_registry_index"),
        }
    )


@login_required
@xframe_options_sameorigin
def ketcher_frame(request):
    """Page that hosts the vendored Ketcher editor; embedded by the Chemical window."""
    return render(request, "internal/lab_tools/ketcher_frame.html")
