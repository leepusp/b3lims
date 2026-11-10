"""Starter notebooks, sharing and "use a copy" for Jupyter notebooks."""

import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import ResearchGroup
from core.services import jupyter_sharing as sharing
from core.services import jupyter_templates as templates


@login_required
def jupyter_shared_view(request, notebook_id):
    notebook = get_object_or_404(sharing.readable_notebooks_for_user(request.user).select_related("owner"), pk=notebook_id)

    return render(request, "internal/lab_tools/jupyter_shared.html", {
        "notebook": notebook,
        "cells": sharing.readable_cells(notebook),
        "is_owner": sharing.can_manage(request.user, notebook),
    })


@login_required
@require_POST
def jupyter_copy(request, notebook_id):
    notebook = get_object_or_404(sharing.readable_notebooks_for_user(request.user), pk=notebook_id)
    copy = sharing.copy_notebook(notebook, request.user)

    messages.success(request, f"Created your own copy: {copy.title}")

    return redirect("jupyter_workspace", notebook_id=copy.pk)


@login_required
@require_POST
def jupyter_from_template(request):
    try:
        notebook = templates.create_notebook(request.user, request.POST.get("template", ""))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])

        return redirect("jupyter_index")

    messages.success(request, f"Created {notebook.title}. It runs as it is on demo data; set its parameters to use your own files.")

    return redirect("jupyter_workspace", notebook_id=notebook.pk)


@login_required
@require_POST
def jupyter_sharing_api(request, notebook_id):
    notebook = get_object_or_404(sharing.readable_notebooks_for_user(request.user), pk=notebook_id)

    try:
        data = json.loads(request.body or "{}")
        action = data.get("action")

        if action == "get":
            if not sharing.can_manage(request.user, notebook):
                raise PermissionDenied("Only the owner can see who a notebook is shared with.")
        elif action == "search":
            if not sharing.can_manage(request.user, notebook):
                raise PermissionDenied("Only the owner can change sharing.")

            return JsonResponse({"status": "success", "results": sharing.search_principals(notebook, data.get("q"))})
        elif action == "set_visibility":
            sharing.set_visibility(notebook, request.user, data.get("visibility"))
        elif action == "add":
            if data.get("kind") == "group":
                group = get_object_or_404(ResearchGroup, pk=int(data.get("principal_id")))
                sharing.share_with(notebook, request.user, research_group=group)
            else:
                person = get_object_or_404(get_user_model(), pk=int(data.get("principal_id")), is_active=True)
                sharing.share_with(notebook, request.user, user=person)
        elif action == "remove":
            sharing.unshare(notebook, request.user, int(data.get("grant_id")))
        else:
            raise ValidationError("Unknown action.")
    except PermissionDenied as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=403)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) else "Invalid request."

        return JsonResponse({"status": "error", "message": message}, status=400)

    notebook.refresh_from_db()

    return JsonResponse({"status": "success", **sharing.sharing_state(notebook)})
