"""Explicit workspace-authorized child creation for Sample forms."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods

from core.models.samples.storage import StorageLocation, StorageWorkspace
from core.permissions.storage_workspaces_v8 import (
    can_view_storage_location,
    can_manage_storage_workspace,
    visible_storage_workspaces_for_user,
)
from core.models.samples.storage import StorageLocationLayoutV8146C3
from core.services.storage_workspace_infrastructure_v8 import (
    create_storage_location_in_workspace_v8,
)
from core.services.storage_workspaces_v8 import create_storage_workspace_v8
from core.views.internal.storage.location_layout_v8146c3 import parse_layout


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


@login_required
@require_http_methods(["GET", "POST"])
def storage_path_register_v8146(request):
    """Register a named hierarchy within an authorized workspace."""

    if request.method == "GET":
        rows = [
            {
                "id": ws.pk,
                "name": ws.name,
                "scope": ws.scope,
            }
            for ws in visible_storage_workspaces_for_user(request.user)
            if can_manage_storage_workspace(request.user, ws)
        ]
        response = JsonResponse({
            "ok": True,
            "workspaces": rows,
        })
        response["Cache-Control"] = "no-store"
        return response

    try:
        token = str(request.POST.get("workspace_id", "")).strip()
        automatic = not token

        if not automatic and not (
            token.isascii()
            and token.isdecimal()
            and 1 <= len(token) <= 18
            and int(token) > 0
        ):
            raise ValidationError(
                "Select an authorized storage workspace."
            )

        raw = request.POST.get("path", "")

        if not isinstance(raw, str) or not raw.strip():
            raise ValidationError("Enter a storage path.")

        if len(raw) > 2600:
            raise ValidationError("Storage path is too long.")

        parts = [part.strip() for part in raw.split(">")]

        if (
            len(parts) > 16
            or any(
                not part
                or len(part) > 150
                or any(c in part for c in (";", ",", "\\n", "\\r"))
                for part in parts
            )
        ):
            raise ValidationError(
                "Use 1 to 16 names of up to 150 characters "
                "without >, commas or semicolons."
            )

        layout_args = (
            parse_layout(request.POST)
            if request.POST.get("organization") else None
        )

        with transaction.atomic():
            workspace_created = False

            if automatic:
                # No workspace chosen: the first level of the path names one.
                if len(parts) < 2:
                    raise ValidationError(
                        "Without a workspace, the first level becomes "
                        "the workspace; add at least one more level."
                    )

                name = parts.pop(0)
                workspace = next((
                    ws for ws in visible_storage_workspaces_for_user(request.user)
                    if ws.name.casefold() == name.casefold()
                    and can_manage_storage_workspace(request.user, ws)
                ), None)

                if workspace is None:
                    workspace = create_storage_workspace_v8(
                        actor=request.user, name=name, scope="personal",
                    )
                    workspace_created = True

                workspace = StorageWorkspace.objects.select_for_update().get(pk=workspace.pk)
            else:
                workspace = (
                    StorageWorkspace.objects.select_for_update()
                    .filter(pk=int(token)).first()
                )

            if (
                workspace is None
                or not can_manage_storage_workspace(
                    request.user, workspace
                )
            ):
                raise PermissionDenied(
                    "Storage workspace management denied."
                )

            parent = None
            created_count = 0
            last_created = None

            for name in parts:
                matches = list(
                    StorageLocation.objects
                    .select_for_update(of=("self",))
                    .filter(
                        workspace=workspace,
                        parent=parent,
                        name__iexact=name,
                    )
                    .order_by("pk")[:2]
                )

                if len(matches) > 1:
                    raise ValidationError(
                        "Ambiguous duplicate storage locations."
                    )

                if matches:
                    node = matches[0]
                    if (
                        not node.is_active
                        or node.location_type == "position"
                        or not can_view_storage_location(
                            request.user, node
                        )
                    ):
                        raise ValidationError(
                            "Storage parent is inactive or inaccessible."
                        )
                else:
                    node = create_storage_location_in_workspace_v8(
                        actor=request.user,
                        workspace_id=workspace.pk,
                        parent_id=parent.pk if parent else None,
                        name=name,
                        location_type="other",
                        rank=None,
                    )
                    created_count += 1
                    last_created = node.pk

                parent = node

            if layout_args and created_count and parent.pk == last_created:
                layout = StorageLocationLayoutV8146C3(location=parent, **layout_args)

                layout.full_clean()
                layout.save()

            anchor = {
                "id": parent.pk,
                "parent_id": parent.parent_id,
                "name": parent.name,
                "location_type": parent.location_type,
                "full_path": parent.full_path,
                "depth": len(parent.full_path_parts) - 1,
                "rank": parent.rank,
            }

    except ValidationError as exc:
        return JsonResponse(
            {"ok": False, "error": " ".join(exc.messages)},
            status=400,
        )
    except PermissionDenied:
        return JsonResponse(
            {"ok": False, "error": "Storage management denied."},
            status=403,
        )
    except IntegrityError:
        return JsonResponse(
            {"ok": False, "error": "Storage hierarchy conflict."},
            status=409,
        )

    response = JsonResponse({
        "ok": True,
        "created_count": created_count,
        "reused_count": len(parts) - created_count,
        "workspace": {"id": workspace.pk, "name": workspace.name, "created": workspace_created},
        "anchor": anchor,
    }, status=201 if created_count else 200)
    response["Cache-Control"] = "no-store"
    return response
