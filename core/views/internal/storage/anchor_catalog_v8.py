"""Catalog endpoint for the Sample registration Path Builder."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.services.storage_anchor_catalog_v8 import (
    build_storage_anchor_catalog,
)


@login_required
@require_GET
@never_cache
def storage_anchor_catalog_v8(request):
    anchors = build_storage_anchor_catalog(user=request.user)

    return JsonResponse({
        "version": 1,
        "anchors": anchors,
        "capacity_available": False,
        "read_only": True,
    })
