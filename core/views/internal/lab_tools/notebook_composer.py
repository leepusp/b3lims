"""JSON endpoints for the composable parts of a Notebook entry (1.A)."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from core.models.lab_tools.notebook_composer import NotebookEntryLink, NotebookStep
from core.services import notebook_composer as composer
from core.views.internal.lab_tools.notebook import _get_entry_for_user


def composer_state(entry, user):
    """Everything the composer UI needs for one entry."""
    return {
        "entry_id": entry.pk,
        "custom_id": entry.custom_id,
        "rating": entry.rating,
        "tags": [tag.name for tag in entry.tags.all()],
        "fields": composer.describe_fields(entry, user),
        "missing_required": composer.missing_required_fields(entry.metadata),
        "steps": composer.serialize_steps(entry),
        "links": composer.serialize_links(entry, user),
    }


def _payload(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Invalid JSON body.")
    if not isinstance(data, dict):
        raise ValidationError("Invalid JSON body.")
    return data


def _error(exc):
    messages = getattr(exc, "messages", None) or [str(exc)]
    return JsonResponse({"status": "error", "message": " ".join(messages)}, status=400)


def _ok(entry, user):
    return JsonResponse({"status": "success", "state": composer_state(entry, user)})


@login_required
@require_POST
def notebook_fields_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _payload(request)
        entry.metadata = composer.normalize_metadata(
            data.get("metadata"), user=request.user, entry=entry
        )
        entry.save(update_fields=["metadata", "updated_at"])
    except ValidationError as exc:
        return _error(exc)
    return _ok(entry, request.user)


@login_required
@require_POST
def notebook_header_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _payload(request)
        composer.update_header(
            entry,
            custom_id=data.get("custom_id"),
            rating=data.get("rating"),
            tags=data.get("tags"),
        )
    except ValidationError as exc:
        return _error(exc)
    return _ok(entry, request.user)


@login_required
@require_POST
def notebook_steps_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _payload(request)
        action = data.get("action")

        if action == "add":
            composer.add_step(entry, data.get("body"), data.get("deadline"))
        elif action == "reorder":
            composer.reorder_steps(entry, data.get("order") or [])
        elif action in {"update", "delete"}:
            step = get_object_or_404(NotebookStep, pk=data.get("step_id"), entry=entry)
            if action == "delete":
                step.delete()
            else:
                composer.update_step(
                    step,
                    request.user,
                    body=data.get("body"),
                    finished=data.get("finished"),
                    deadline=data.get("deadline"),
                    clear_deadline=bool(data.get("clear_deadline")),
                )
        else:
            raise ValidationError("Unknown step action.")
    except ValidationError as exc:
        return _error(exc)
    return _ok(entry, request.user)


@login_required
@require_POST
def notebook_entry_links_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _payload(request)
        action = data.get("action")
        if action == "add":
            composer.add_entry_link(entry, data.get("target_id"), request.user)
        elif action == "remove":
            NotebookEntryLink.objects.filter(entry=entry, target_id=data.get("target_id")).delete()
        else:
            raise ValidationError("Unknown link action.")
    except ValidationError as exc:
        return _error(exc)
    return _ok(entry, request.user)


@login_required
@require_GET
def notebook_lookup_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    kind = request.GET.get("kind", "")
    if kind not in composer.REFERENCE_TYPES:
        return JsonResponse({"status": "error", "message": "Unknown kind."}, status=400)
    results = composer.search_references(kind, request.user, request.GET.get("q", ""), entry=entry)
    return JsonResponse({"status": "success", "results": results})


@login_required
@require_GET
def notebook_field_definitions_api(request, entry_id):
    """Field structure of a visible entry, to load into another one."""
    source = _get_entry_for_user(entry_id, request.user)
    return JsonResponse(
        {"status": "success", "metadata": composer.field_definitions_from(source)}
    )
