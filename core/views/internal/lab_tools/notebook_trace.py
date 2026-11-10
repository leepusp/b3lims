"""API for signatures and deviations of a Notebook entry."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from core.permissions.notebook import visible_notebook_entries_for_user
from core.services import notebook_trace as trace


@login_required
@require_POST
def notebook_trace_api(request, entry_id):
    entry = get_object_or_404(visible_notebook_entries_for_user(request.user), pk=entry_id)

    try:
        data = json.loads(request.body or "{}")
        action = data.get("action", "state")

        if action == "sign":
            trace.sign(entry, request.user, data.get("meaning"), data.get("comment"))
        elif action == "amend":
            trace.amend(entry, request.user, data.get("reason"))
        elif action == "add_deviation":
            trace.add_deviation(entry, request.user, data.get("description"), data.get("impact", "minor"), data.get("step"))
        elif action == "resolve_deviation":
            trace.resolve_deviation(entry, request.user, data.get("id"), data.get("resolution"))
        elif action != "state":
            raise ValidationError("Unknown action.")
    except PermissionDenied as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=403)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) else "Invalid request."

        return JsonResponse({"status": "error", "message": message}, status=400)

    entry.refresh_from_db()

    return JsonResponse({"status": "success", "trace": trace.state(entry, request.user)})
