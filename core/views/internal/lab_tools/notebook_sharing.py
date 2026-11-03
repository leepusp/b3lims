"""Sharing API for Notebook entries (who can read, edit and share)."""

import json
from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.models import ResearchGroup
from core.permissions.notebook import (
    can_edit_notebook_entry,
    can_manage_notebook_entry_sharing,
    grant_level,
)
from core.services import notebook_sharing
from core.views.internal.lab_tools.notebook import _get_entry_for_user


def _err(message, status=400):
    return JsonResponse({"status": "error", "message": str(message)}, status=status)


def _state(entry, user):
    can_manage = can_manage_notebook_entry_sharing(user, entry)
    return {
        "status": "success",
        "visibility": entry.visibility,
        "visibilities": [{"value": v, "label": l} for v, l in notebook_sharing.VISIBILITIES],
        "levels": [{"value": v, "label": l} for v, l in notebook_sharing.LEVELS],
        "can_manage": can_manage,
        "can_edit": can_edit_notebook_entry(user, entry),
        "your_access": (
            "author" if entry.author_id == user.pk
            else "admin" if user.is_superuser
            else grant_level(user, entry) or ("lab" if entry.visibility == "lab" else None)
        ),
        "author": entry.author.get_full_name() or entry.author.get_username(),
        # Only people who can manage see the full list; others see a count.
        "grants": [notebook_sharing.grant_payload(g) for g in notebook_sharing.entry_grants(entry)]
        if can_manage
        else [],
    }


def _expiry(value):
    if not value:
        return None
    try:
        day = date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValidationError("The expiration date must look like YYYY-MM-DD.")
    # Valid through the end of the chosen day, in the lab's time zone.
    return timezone.make_aware(datetime.combine(day, time(23, 59)), timezone.get_current_timezone())


@login_required
@require_http_methods(["GET", "POST"])
def notebook_sharing_api(request, entry_id):
    """GET: sharing state, or ``?q=ana`` to look up users and groups.

    POST ``{action: grant|revoke|visibility, ...}`` (author, superuser or manage grant).
    """
    entry = _get_entry_for_user(entry_id, request.user)

    if request.method == "GET":
        query = request.GET.get("q")
        if query is not None:
            if not can_manage_notebook_entry_sharing(request.user, entry):
                return _err("You cannot manage this entry's sharing.", 403)
            return JsonResponse(
                {"status": "success", "results": notebook_sharing.search_principals(query=query, entry=entry)}
            )
        return JsonResponse(_state(entry, request.user))

    try:
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            raise ValidationError("Invalid request body.")
        if not isinstance(data, dict):
            raise ValidationError("Invalid request body.")
        action = data.get("action")

        if action == "grant":
            user = group = None
            if data.get("kind") == "group":
                group = get_object_or_404(ResearchGroup, pk=data.get("principal_id"))
            elif data.get("kind") == "user":
                user = get_object_or_404(get_user_model(), pk=data.get("principal_id"))
            else:
                raise ValidationError("Choose a user or a research group.")
            notebook_sharing.share_entry(
                entry=entry,
                granted_by=request.user,
                level=data.get("level"),
                user=user,
                research_group=group,
                expires_at=_expiry(data.get("expires")),
            )
        elif action == "revoke":
            notebook_sharing.unshare_entry(entry=entry, grant_id=data.get("grant_id"), revoked_by=request.user)
        elif action == "visibility":
            notebook_sharing.set_visibility(entry=entry, value=data.get("value"), changed_by=request.user)
        else:
            raise ValidationError("Unknown action.")
    except PermissionDenied as exc:
        return _err(exc, 403)
    except ValidationError as exc:
        return _err(" ".join(exc.messages))
    entry.refresh_from_db()
    return JsonResponse(_state(entry, request.user))
