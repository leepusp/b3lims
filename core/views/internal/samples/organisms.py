from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.services import sample_organisms


@login_required
@require_GET
def organism_search_api(request):
    """Taxa from the local taxonomy database for the organism picker, limited to the sample type's branch."""
    query = (request.GET.get("q") or "").strip()[:100]
    sample_type = (request.GET.get("type") or "").strip()[:100]

    if len(query) < 2:
        return JsonResponse({"status": "success", "available": True, "results": [], "scope": sample_organisms.scope_label(sample_type)})

    return JsonResponse({"status": "success", **sample_organisms.search(query, sample_type)})


@login_required
@require_GET
def organism_details_api(request):
    """Names, lineage, GTDB reference data and inferred virus traits of one taxon of the local taxonomy."""
    taxid = (request.GET.get("taxid") or "").strip()

    if not taxid.isdigit():
        return JsonResponse({"status": "error", "message": "A numeric taxonomy id is required."}, status=400)

    found = sample_organisms.details(taxid, (request.GET.get("type") or "")[:100])

    if found is None:
        return JsonResponse({"status": "error", "message": "Taxon not found in the local taxonomy database."}, status=404)

    return JsonResponse({"status": "success", **found})
