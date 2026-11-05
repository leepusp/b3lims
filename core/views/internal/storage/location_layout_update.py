"""Edit the drawing of an existing storage location."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from core.services.storage_layout_edit import update_location_layout


@login_required
@require_POST
def storage_location_layout_update(request):
    try:
        location, layout, renamed = update_location_layout(
            actor=request.user,
            location_id=request.POST.get("location_id"),
            organization=str(request.POST.get("organization", "")).strip(),
            rows=request.POST.get("rows"),
            columns=request.POST.get("columns"),
            slot_labels=request.POST.getlist("slot_label"),
            slot_old=request.POST.getlist("slot_old"),
            direction=request.POST.get("slot_direction") or "column",
        )
        text = {
            "grid": f"grid {layout.rows} x {layout.columns}",
            "slots": f"{len(layout.slot_labels)} compartments",
            "free": "no drawing",
        }[layout.organization]
        extra = f" {renamed} renamed with their Samples." if renamed else ""
        messages.success(
            request, f"Drawing of '{location.name}' updated: {text}.{extra}"
        )
    except PermissionDenied:
        messages.error(
            request, "You are not authorized to manage this storage location."
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except IntegrityError:
        messages.error(request, "Storage conflict. Reload and try again.")

    return redirect("storage_workspace")
