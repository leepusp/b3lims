"""Find Samples by ID for the storage drawing (placed or not yet placed)."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.permissions.samples import visible_samples_for_user
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
)

LIMIT = 15


@login_required
@require_GET
@never_cache
def storage_sample_search(request):
    query = " ".join(request.GET.get("q", "").split())[:60]

    if len(query) < 2:
        return JsonResponse({"results": []})

    found = (
        visible_samples_for_user(request.user)
        .filter(sample_id__icontains=query)
        .order_by("sample_id")[: LIMIT * 3]
    )
    results = []

    for sample in found:
        if not can_operate_on_sample_storage(request.user, sample):
            continue

        place = (
            sample.storage_assignments.select_related("location")
            .filter(status="active", is_primary=True)
            .first()
        )
        results.append({
            "id": sample.pk,
            "sample": sample.sample_id,
            "where": (
                place.location.full_path
                + (f" › {place.position}" if place.position else "")
                if place else ""
            ),
        })

        if len(results) >= LIMIT:
            break

    return JsonResponse({"results": results})
