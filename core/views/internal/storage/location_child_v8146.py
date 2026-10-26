"""Explicit workspace-authorized child creation for Sample forms."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.models.samples.storage import StorageLocation
from core.permissions.storage_workspaces_v8 import (
    can_view_storage_location,
)
from core.services.storage_workspace_infrastructure_v8 import (
    create_storage_location_in_workspace_v8,
)


def _positive_id(value):
    value = str(value or "").strip()

    if not (
        1 <= len(value) <= 18
        and value.isascii()
        and value.isdecimal()
        and int(value) > 0
    ):
        raise ValidationError(
            "Select an existing parent location."
        )

    return int(value)


@login_required
@require_POST
def storage_location_child_create_v8146(request):
    """
    Create one named child under an existing physical parent.

    Workspace is derived from the parent, never from the POST body.
    This operation does not create or move any Sample assignment.
    """
    try:
        parent_id = _positive_id(
            request.POST.get("parent_id")
        )

        parent = StorageLocation.objects.filter(
            pk=parent_id
        ).first()

        if parent is None:
            raise ValidationError(
                "Select an existing parent location."
            )

        if (
            parent.workspace_id is None
            or not can_view_storage_location(
                request.user, parent
            )
        ):
            raise PermissionDenied(
                "Storage infrastructure modification denied."
            )

        name = request.POST.get("name", "")

        location_type = request.POST.get(
            "location_type", "other"
        )

        created = create_storage_location_in_workspace_v8(
            actor=request.user,
            workspace_id=parent.workspace_id,
            parent_id=parent.pk,
            name=name,
            location_type=location_type,
            rank=1,
        )

    except ValidationError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": " ".join(exc.messages),
            },
            status=400,
        )

    except PermissionDenied:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "You are not authorized to create "
                    "locations in this workspace."
                ),
            },
            status=403,
        )

    except IntegrityError:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "A conflicting location was created. "
                    "Reload the hierarchy and try again."
                ),
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            "created": True,
            "anchor": {
                "id": created.pk,
                "parent_id": created.parent_id,
                "name": created.name,
                "location_type": created.location_type,
                "full_path": created.full_path,
                "depth": len(created.full_path_parts) - 1,
                "rank": created.rank,
            },
        },
        status=201,
    )
