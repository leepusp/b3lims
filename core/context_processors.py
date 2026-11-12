"""Values every page needs: who runs this installation and which optional features are on."""

from django.conf import settings


def installation(request):
    from core.services import interface_settings

    hidden = interface_settings.current()

    return {
        "ui_hidden": hidden["features"],
        "ui_hidden_types": hidden["types"],
        "org_name": getattr(settings, "BIOBANK_ORG_NAME", "") or "B3 LIMS",
        "jupyter_enabled": getattr(settings, "BIOBANK_JUPYTER_ENABLED", False),
    }
