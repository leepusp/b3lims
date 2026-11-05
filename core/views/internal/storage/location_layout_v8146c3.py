"""Create a storage location together with its optional layout."""

import unicodedata

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from core.models.samples.storage import (
    StorageLocationLayoutV8146C3,
    clean_slot_labels,
)
from core.services.storage_workspace_infrastructure_v8 import (
    create_storage_location_in_workspace_v8,
)


def _positive_dimension(value, *, maximum, label):
    token = str(value or "").strip()

    if not (
        token.isascii()
        and token.isdecimal()
        and 1 <= len(token) <= 3
        and 1 <= int(token) <= maximum
    ):
        raise ValidationError(
            f"{label} must be between 1 and {maximum}."
        )

    return int(token)


def _optional_label(value, *, maximum, label):
    text = str(value or "").strip()

    if len(text) > maximum:
        raise ValidationError(
            f"{label} exceeds {maximum} characters."
        )

    if any(
        unicodedata.category(char).startswith("C")
        for char in text
    ):
        raise ValidationError(
            f"{label} contains invalid control characters."
        )

    return text


@login_required
@require_POST
def storage_location_create_with_layout_v8146c3(request):
    """Create a scoped location and its layout atomically."""

    try:
        if request.POST.get("action") != "create_location":
            raise ValidationError("Invalid storage creation action.")

        organization = str(
            request.POST.get("organization", "")
        ).strip()

        if organization not in {"free", "grid", "slots"}:
            raise ValidationError(
                "Select a valid storage organization."
            )

        if organization == "grid":
            rows = _positive_dimension(
                request.POST.get("rows"),
                maximum=26,
                label="Rows",
            )
            columns = _positive_dimension(
                request.POST.get("columns"),
                maximum=24,
                label="Columns",
            )
        else:
            rows = 0
            columns = 0

        slot_labels = []
        slot_direction = "column"

        if organization == "slots":
            slot_labels = clean_slot_labels(
                request.POST.getlist("slot_label")
            )
            slot_direction = (
                request.POST.get("slot_direction") or "column"
            )
            if slot_direction not in {"column", "row"}:
                raise ValidationError(
                    "Select a valid compartment direction."
                )

        if organization != "grid":
            if any(
                str(request.POST.get(field, "")).strip()
                for field in ("rows", "columns")
            ):
                raise ValidationError(
                    "Only a position grid can specify grid dimensions."
                )

        type_label = _optional_label(
            request.POST.get("type_label"),
            maximum=80,
            label="Descriptive type",
        )

        temperature_label = _optional_label(
            request.POST.get("temperature_label"),
            maximum=60,
            label="Temperature",
        )

        with transaction.atomic():
            location = create_storage_location_in_workspace_v8(
                actor=request.user,
                workspace_id=request.POST.get("workspace_id"),
                parent_id=request.POST.get("parent_id") or None,
                name=request.POST.get("name", ""),
                location_type=request.POST.get(
                    "location_type", "other"
                ),
                rank=request.POST.get("rank", 1),
                notes=request.POST.get("notes", ""),
            )

            layout = StorageLocationLayoutV8146C3(
                location=location,
                organization=organization,
                rows=rows,
                columns=columns,
                slot_labels=slot_labels,
                slot_direction=slot_direction,
                type_label=type_label,
                temperature_label=temperature_label,
            )

            layout.full_clean()
            layout.save()

        description = (
            f"{rows} x {columns} ({rows * columns} positions)"
            if organization == "grid"
            else f"{len(slot_labels)} compartments"
            if organization == "slots"
            else "free organization"
        )

        messages.success(
            request,
            f"Storage location '{location.name}' created: "
            f"{description}.",
        )

    except PermissionDenied:
        messages.error(
            request,
            "You are not authorized to manage this storage location.",
        )

    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))

    except IntegrityError:
        messages.error(
            request,
            "Storage location conflict. Reload and try again.",
        )

    return redirect("storage_workspace")
