"""Workspace-scoped physical storage infrastructure operations."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.permissions.storage_workspaces_v8 import (
    can_manage_storage_workspace,
    is_storage_global_admin,
)
from core.services.storage_locations import (
    create_storage_location,
    update_storage_location,
    set_storage_location_active,
)
from core.services.storage_writer_lock import (
    acquire_storage_writer_lock,
)


def _clean_name(name):
    value = str(name or "").strip()

    if not value or len(value) > 150:
        raise ValidationError(
            "Storage location name must contain 1–150 characters."
        )

    if any(char in value for char in (">", ";", ",")):
        raise ValidationError(
            "Storage location name cannot contain >, ; or ,."
        )

    return value


def _clean_type(location_type):
    value = str(location_type or "").strip().lower()

    allowed = {
        choice[0]
        for choice in StorageLocation.LOCATION_TYPE_CHOICES
    } - {"position"}

    if value not in allowed:
        raise ValidationError(
            "Select a valid physical location type."
        )

    return value


def _clean_rank(rank):
    if isinstance(rank, bool):
        raise ValidationError("Invalid storage rank.")

    try:
        value = int(rank)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Storage rank must be a positive integer."
        ) from exc

    if (
        value < 1
        or value > 1000000
        or str(rank).strip() != str(value)
    ):
        raise ValidationError(
            "Storage rank must be a positive integer."
        )

    return value


def _managed_workspace(actor, workspace_id):
    try:
        workspace_id = int(workspace_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Select a storage workspace."
        ) from exc

    workspace = (
        StorageWorkspace.objects
        .select_for_update()
        .filter(pk=workspace_id)
        .first()
    )

    if (
        workspace is None
        or not can_manage_storage_workspace(actor, workspace)
    ):
        raise PermissionDenied(
            "You cannot manage this storage workspace."
        )

    return workspace


def _check_ancestors(location, workspace_id, *, active=False):
    visited = set()
    node = location

    while node is not None:
        if node.pk in visited:
            raise ValidationError(
                "Cyclic physical storage hierarchy."
            )

        visited.add(node.pk)

        if node.workspace_id != workspace_id:
            raise PermissionDenied(
                "Mixed-workspace hierarchy is not permitted."
            )

        if active and not node.is_active:
            raise ValidationError(
                "The parent storage hierarchy is inactive."
            )

        node = node.parent


def _managed_location(actor, location_id):
    try:
        location_id = int(location_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Select a valid storage location."
        ) from exc

    location = (
        StorageLocation.objects
        .select_for_update(of=("self",))
        .select_related("workspace", "parent")
        .filter(pk=location_id)
        .first()
    )

    if location is None:
        raise PermissionDenied(
            "Storage location is not accessible."
        )

    if location.workspace_id is None:
        if not is_storage_global_admin(actor):
            raise PermissionDenied(
                "Unscoped legacy storage is administrator-only."
            )
    elif not can_manage_storage_workspace(
        actor, location.workspace
    ):
        raise PermissionDenied(
            "You cannot manage this physical location."
        )

    _check_ancestors(location, location.workspace_id)

    return location


@transaction.atomic
def create_storage_location_in_workspace_v8(
    *,
    actor,
    workspace_id,
    name,
    location_type,
    parent_id=None,
    rank=1,
    notes="",
):
    """Create a physical node inside an authorized workspace."""
    acquire_storage_writer_lock()

    workspace = _managed_workspace(actor, workspace_id)
    name = _clean_name(name)
    location_type = _clean_type(location_type)
    automatic_rank = rank in (None, "")
    rank = 1 if automatic_rank else _clean_rank(rank)

    parent = None

    if parent_id not in (None, ""):
        try:
            pk = int(parent_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Select a valid parent location."
            ) from exc

        parent = (
            StorageLocation.objects
            .select_for_update(of=("self",))
            .select_related("parent")
            .filter(pk=pk)
            .first()
        )

        if (
            parent is None
            or parent.workspace_id != workspace.pk
        ):
            raise PermissionDenied(
                "Parent location is not in this workspace."
            )

        _check_ancestors(
            parent,
            workspace.pk,
            active=True,
        )

    if StorageLocation.objects.filter(
        parent=parent,
        workspace=workspace,
        name__iexact=name,
    ).exists():
        raise ValidationError(
            "A location with this name already exists "
            "under the selected parent."
        )

    if automatic_rank:
        # New levels go after their siblings; order is changed later by moving.
        last = (
            StorageLocation.objects
            .filter(parent=parent, workspace=workspace)
            .order_by("-rank")
            .values_list("rank", flat=True)
            .first()
        )
        rank = (last or 0) + 1

    # Reuse the existing hierarchy validation service.
    # The unscoped intermediate object is inside this transaction
    # and is not exposed as committed inventory.
    location = create_storage_location(
        name=name,
        parent=parent,
        location_type=location_type,
        rank=rank,
        notes=str(notes or ""),
    )

    location.workspace = workspace
    location.full_clean()
    location.save(update_fields=["workspace"])

    return location


@transaction.atomic
def update_storage_location_in_workspace_v8(
    *,
    actor,
    location_id,
    name,
    location_type,
    rank=1,
    notes="",
):
    """Update an existing physical node without changing ownership."""
    acquire_storage_writer_lock()

    location = _managed_location(actor, location_id)
    name = _clean_name(name)
    location_type = _clean_type(location_type)
    rank = _clean_rank(rank)

    if StorageLocation.objects.filter(
        parent_id=location.parent_id,
        workspace_id=location.workspace_id,
        name__iexact=name,
    ).exclude(pk=location.pk).exists():
        raise ValidationError(
            "Another location already uses this name."
        )

    update_storage_location(
        location,
        name=name,
        location_type=location_type,
        rank=rank,
        notes=str(notes or ""),
    )

    location.refresh_from_db()

    if location.workspace_id is None:
        if not is_storage_global_admin(actor):
            raise PermissionDenied(
                "Legacy inventory requires administration."
            )

    return location


@transaction.atomic
def set_storage_location_active_in_workspace_v8(
    *,
    actor,
    location_id,
    is_active,
):
    """Change lifecycle state only within an authorized workspace."""
    acquire_storage_writer_lock()

    if not isinstance(is_active, bool):
        raise ValidationError(
            "Storage activation state must be a boolean."
        )

    location = _managed_location(actor, location_id)

    set_storage_location_active(
        location,
        is_active=is_active,
    )

    location.refresh_from_db()

    return location
