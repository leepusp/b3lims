from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def healthz_view(request):
    checks = {
        "status": "ok",
        "database": {
            "vendor": connection.vendor,
            "name": connection.settings_dict.get("NAME"),
        },
        "media": {
            "root": str(settings.MEDIA_ROOT),
            "exists": Path(settings.MEDIA_ROOT).exists(),
            "is_dir": Path(settings.MEDIA_ROOT).is_dir(),
        },
        "counts": {},
    }

    for label in [
        "core.Sample",
        "core.SampleFile",
        "core.Shipment",
        "core.ShipmentDocument",
        "core.NotebookEntry",
    ]:
        model = apps.get_model(label)
        checks["counts"][label] = model.objects.count()

    if connection.vendor != "postgresql":
        checks["status"] = "error"
        checks["database"]["error"] = "Expected PostgreSQL backend."

    if not checks["media"]["exists"] or not checks["media"]["is_dir"]:
        checks["status"] = "error"
        checks["media"]["error"] = "MEDIA_ROOT is not available."

    status_code = 200 if checks["status"] == "ok" else 500
    return JsonResponse(checks, status=status_code)
