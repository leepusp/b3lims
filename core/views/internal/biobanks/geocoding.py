from django.contrib.auth.decorators import (
    login_required,
)
from django.http import JsonResponse
from django.views.decorators.http import (
    require_GET,
)

from core.services.geocoding import (
    GeocodingUnavailable,
    reverse_location,
    search_locations,
)


@login_required
@require_GET
def biobank_geocode_search_view(
    request,
):
    query = (
        request.GET.get("q")
        or ""
    ).strip()

    try:
        results = search_locations(
            query,
            limit=5,
        )

    except ValueError as exc:
        return JsonResponse(
            {
                "error": str(exc),
                "results": [],
            },
            status=400,
        )

    except GeocodingUnavailable:
        return JsonResponse(
            {
                "error": (
                    "Address search is "
                    "temporarily unavailable."
                ),
                "results": [],
            },
            status=503,
        )

    return JsonResponse(
        {
            "results": results,
        }
    )


@login_required
@require_GET
def biobank_geocode_reverse_view(
    request,
):
    lat = request.GET.get(
        "lat"
    )

    lon = request.GET.get(
        "lon"
    )

    try:
        result = reverse_location(
            lat,
            lon,
        )

    except ValueError as exc:
        return JsonResponse(
            {
                "error": str(exc),
                "result": None,
            },
            status=400,
        )

    except GeocodingUnavailable:
        return JsonResponse(
            {
                "error": (
                    "Address lookup is "
                    "temporarily unavailable."
                ),
                "result": None,
            },
            status=503,
        )

    return JsonResponse(
        {
            "result": result,
        }
    )
