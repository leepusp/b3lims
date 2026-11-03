"""Pages and API to edit the status and category lists (lab default or one research group)."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from core.models import NotebookCategory, NotebookStatus, ResearchGroup
from core.services import notebook_taxonomy as svc


def _err(message, status=400):
    return JsonResponse({"status": "error", "message": str(message)}, status=status)


def _scope(request, raw):
    """``lab`` or empty -> the lab default list (superusers only); otherwise a group id."""
    if raw in (None, "", "lab"):
        return None
    return get_object_or_404(ResearchGroup, pk=raw)


def _payload(group):
    return {
        "status": "success",
        "group": group.pk if group else None,
        "statuses": [
            {"id": s.pk, "slug": s.slug, "name": s.name, "color": s.color, "kind": s.kind,
             "protected": s.slug in svc.PROTECTED_SLUGS}
            for s in NotebookStatus.objects.filter(**svc.scope_filter(group))
        ],
        "categories": [
            {"id": c.pk, "name": c.name, "color": c.color}
            for c in NotebookCategory.objects.filter(**svc.scope_filter(group))
        ],
        "kinds": [{"value": v, "label": l} for v, l in NotebookStatus.Kind.choices],
    }


@login_required
def notebook_taxonomy_page(request):
    groups = svc.editable_groups(request.user)
    if not groups and not request.user.is_superuser:
        raise PermissionDenied("Only research group coordinators and superusers edit these lists.")
    return render(
        request,
        "internal/lab_tools/notebook_taxonomy.html",
        {"groups": groups, "can_edit_lab": request.user.is_superuser},
    )


@login_required
@require_http_methods(["GET", "POST"])
def notebook_taxonomy_api(request):
    if request.method == "GET":
        group = _scope(request, request.GET.get("group"))
        # Everyone may read a list (entries show it); editing is checked on POST.
        return JsonResponse(_payload(group))

    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return _err("Invalid request body.")
    group = _scope(request, data.get("group"))
    action = data.get("action")
    try:
        if action == "add_status":
            svc.create_status(user=request.user, group=group, name=data.get("name"),
                              color=data.get("color") or "#6b7280", kind=data.get("kind") or "active")
        elif action == "edit_status":
            status = get_object_or_404(NotebookStatus, pk=data.get("id"), **svc.scope_filter(group))
            svc.update_status(user=request.user, status=status, name=data.get("name"),
                              color=data.get("color"), kind=data.get("kind"))
        elif action == "delete_status":
            status = get_object_or_404(NotebookStatus, pk=data.get("id"), **svc.scope_filter(group))
            svc.delete_status(user=request.user, status=status)
        elif action == "add_category":
            svc.create_category(user=request.user, group=group, name=data.get("name"),
                                color=data.get("color") or "#6b7280")
        elif action == "edit_category":
            cat = get_object_or_404(NotebookCategory, pk=data.get("id"), **svc.scope_filter(group))
            svc.update_category(user=request.user, category=cat, name=data.get("name"), color=data.get("color"))
        elif action == "delete_category":
            cat = get_object_or_404(NotebookCategory, pk=data.get("id"), **svc.scope_filter(group))
            svc.delete_category(user=request.user, category=cat)
        elif action in {"reorder_statuses", "reorder_categories"}:
            ids = data.get("ids")
            if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
                raise ValidationError("Invalid order.")
            model = NotebookStatus if action == "reorder_statuses" else NotebookCategory
            svc.reorder(user=request.user, model=model, group=group, ids=ids)
        else:
            raise ValidationError("Unknown action.")
    except PermissionDenied as exc:
        return _err(exc, 403)
    except ValidationError as exc:
        return _err(" ".join(exc.messages))
    return JsonResponse(_payload(group))
