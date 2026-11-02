"""Experimental ELN entry point. No backend data access yet."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.views.internal.lab_tools.eln_demo_data import build_demo_preview

from core.permissions.eln_experimental import (
    can_access_eln_experimental,
    is_eln_experimental_enabled,
)


@login_required
@require_GET
@never_cache
def eln_experimental_index(request):
    if not is_eln_experimental_enabled():
        raise Http404("ELN Experimental is disabled.")

    if not can_access_eln_experimental(request.user):
        return HttpResponseForbidden(
            "ELN Experimental access is restricted."
        )

    preview = build_demo_preview(request.GET)

    return render(
        request,
        "internal/lab_tools/eln_experimental/index.html",
        {
            "eln_integration_state": "pending",
            "eln_experiments": preview["entries"],
            "pinned": preview["pinned"],
            "categories": preview["categories"],
            "statuses": preview["statuses"],
            "query": preview["query"],
            "selected_category": preview["selected_category"],
            "selected_status": preview["selected_status"],
            "scope": preview["scope"],
            "demo_total": preview["demo_total"],
        },
    )
