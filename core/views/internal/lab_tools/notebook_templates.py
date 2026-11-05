"""Pages and API for user-made entry templates."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from core.models import NotebookTemplate, ResearchGroup
from core.services import custom_field_layout as layout
from core.services import notebook_taxonomy
from core.services import notebook_templates as svc
from core.views.internal.lab_tools.notebook import _get_entry_for_user


def _err(message, status=400):
    return JsonResponse({"status": "error", "message": str(message)}, status=status)


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise ValidationError("Invalid request body.")
    if not isinstance(data, dict):
        raise ValidationError("Invalid request body.")
    return data


def _group(data):
    raw = data.get("research_group")
    if raw in (None, ""):
        return None
    return get_object_or_404(ResearchGroup, pk=raw)


def _payload(template, user):
    return {
        "id": template.pk,
        "key": svc.key_for(template),
        "name": template.name,
        "description": template.description,
        "icon": template.icon,
        "entry_type": template.entry_type,
        "visibility": template.visibility,
        "research_group": template.research_group_id,
        "group_name": template.research_group.name if template.research_group else "",
        "owner": (template.owner.get_full_name() or template.owner.get_username()) if template.owner else "",
        "can_edit": svc.can_edit(user, template),
        "fields": len(layout.fields_of(template.structure)),
        "steps": len((template.structure or {}).get("steps") or []),
        "updated_at": template.updated_at.strftime("%Y-%m-%d"),
    }


def _state(user):
    return {
        "status": "success",
        "templates": [_payload(t, user) for t in svc.templates_for(user)],
        "groups": [{"id": g.pk, "name": g.name} for g in notebook_taxonomy.editable_groups(user)],
        "can_share_lab": user.is_superuser,
        "visibilities": [{"value": v, "label": l} for v, l in NotebookTemplate.Visibility.choices],
    }


@login_required
def notebook_templates_page(request):
    return render(request, "internal/lab_tools/notebook_templates.html", {})


@login_required
@require_http_methods(["GET", "POST"])
def notebook_templates_api(request):
    if request.method == "GET":
        return JsonResponse(_state(request.user))
    try:
        data = _body(request)
        template = get_object_or_404(svc.templates_for(request.user), pk=data.get("id"))
        action = data.get("action")
        if action == "update":
            svc.update_template(
                user=request.user,
                template=template,
                name=data.get("name"),
                description=data.get("description"),
                icon=data.get("icon"),
                visibility=data.get("visibility"),
                group=_group(data),
            )
        elif action == "delete":
            svc.delete_template(user=request.user, template=template)
        else:
            raise ValidationError("Unknown action.")
    except PermissionDenied as exc:
        return _err(exc, 403)
    except ValidationError as exc:
        return _err(" ".join(exc.messages))
    return JsonResponse(_state(request.user))


@login_required
@require_POST
def notebook_entry_save_template(request, entry_id):
    """Make a template from this entry, or refresh an existing one with ``template_id``."""
    entry = _get_entry_for_user(entry_id, request.user)
    try:
        data = _body(request)
        template = None
        if data.get("template_id"):
            template = get_object_or_404(svc.templates_for(request.user), pk=data["template_id"])
        saved = svc.save_entry_as_template(
            entry=entry,
            user=request.user,
            name=data.get("name") or (template.name if template else ""),
            description=data.get("description", template.description if template else ""),
            visibility=data.get("visibility") or (template.visibility if template else "private"),
            group=_group(data) if "research_group" in data else (template.research_group if template else None),
            template=template,
        )
    except PermissionDenied as exc:
        return _err(exc, 403)
    except ValidationError as exc:
        return _err(" ".join(exc.messages))
    return JsonResponse({"status": "success", "template": _payload(saved, request.user)})


@login_required
@require_http_methods(["GET"])
def notebook_entry_template_options(request, entry_id):
    """What the "Save as template" dialog needs: groups to share with and templates the user can overwrite."""
    _get_entry_for_user(entry_id, request.user)
    state = _state(request.user)
    state["templates"] = [t for t in state["templates"] if t["can_edit"]]
    return JsonResponse(state)
