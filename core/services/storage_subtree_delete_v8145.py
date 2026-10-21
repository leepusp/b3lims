"""Authorized deletion of empty physical storage subtrees."""

import json

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.permissions.storage_workspaces_v8 import (
    can_manage_storage_workspace,
)


def _analyze(actor, location_id, *, lock=False):
    raw_id = str(location_id or "").strip()

    if not raw_id.isdecimal():
        raise ValidationError("Invalid storage location.")

    queryset = StorageLocation.objects.select_related("workspace")

    root = queryset.filter(pk=int(raw_id)).first()

    if root is None:
        raise ValidationError("Storage location not found.")

    if (
        root.workspace_id is None
        or not can_manage_storage_workspace(actor, root.workspace)
    ):
        raise PermissionDenied(
            "You cannot remove this storage location."
        )

    locations = StorageLocation.objects.filter(
        workspace_id=root.workspace_id
    ).order_by("pk")

    if lock:
        locations = locations.select_for_update()

    rows = list(
        locations.values("pk", "parent_id")
    )

    children = {}

    for row in rows:
        children.setdefault(row["parent_id"], []).append(
            row["pk"]
        )

    pending = [root.pk]
    visited = set()

    while pending:
        pk = pending.pop()

        if pk in visited:
            raise ValidationError(
                "A cycle exists in this storage hierarchy."
            )

        visited.add(pk)
        pending.extend(children.get(pk, []))

    ids = sorted(visited)

    # Do not allow cross-workspace descendants to be
    # silently removed by the self-referential CASCADE.
    if StorageLocation.objects.filter(
        parent_id__in=ids
    ).exclude(
        workspace_id=root.workspace_id
    ).exists():
        raise ValidationError(
            "The subtree contains inconsistent workspace links."
        )

    assignments = SampleStorageAssignment.objects.filter(
        location_id__in=ids
    )

    sample_count = (
        assignments.values("sample_id").distinct().count()
    )

    # Any assignment, including an inactive assignment,
    # must survive. It is never deleted by this service.
    assignment_count = assignments.count()

    # The historical textual field may still refer to a
    # location without a structured assignment.
    from core.models.samples.sample import Sample
    from django.db.models import Q

    # full_path is a Python property, not a database field.
    paths = [
        item.full_path
        for item in StorageLocation.objects.filter(
            pk__in=ids
        )
    ]

    text_query = Q()

    for path in paths:
        if path:
            text_query |= Q(storage_location__icontains=path)

    textual_count = (
        Sample.objects.filter(text_query).count()
        if paths
        else 0
    )

    # Refuse to delete anything referenced by another
    # application model, including movement history.
    blockers = {}

    for relation in StorageLocation._meta.related_objects:
        model = relation.related_model
        field = relation.field

        if (
            model is StorageLocation
            and field.name == "parent"
        ):
            continue

        if model is SampleStorageAssignment:
            continue

        count = model._default_manager.filter(
            **{f"{field.name}__in": ids}
        ).count()

        if count:
            blockers[model._meta.label] = (
                blockers.get(model._meta.label, 0) + count
            )

    # Movement snapshots are not always foreign keys.
    from core.models.samples.storage import StorageMovementItem

    snapshot_field = {
        field.name
        for field in StorageMovementItem._meta.fields
    }

    if "location_id_snapshot" in snapshot_field:
        snapshot_count = StorageMovementItem.objects.filter(
            location_id_snapshot__in=ids
        ).count()

        if snapshot_count:
            blockers["StorageMovementItem snapshots"] = snapshot_count

    # Movement history can reference storage locations
    # through textual path snapshots without live FKs.
    # Such records must prevent physical deletion.
    if paths:
        from core.models.samples.storage import StorageMovement

        movement_paths = Q()
        item_paths = Q()

        for path in paths:
            if not path:
                continue

            movement_paths |= (
                Q(origin_path__icontains=path)
                | Q(destination_path__icontains=path)
            )

            item_paths |= (
                Q(path_before__icontains=path)
                | Q(path_after__icontains=path)
            )

        movement_count = StorageMovement.objects.filter(
            movement_paths
        ).count()

        item_count = StorageMovementItem.objects.filter(
            item_paths
        ).count()

        if movement_count:
            blockers["StorageMovement path snapshots"] = (
                movement_count
            )

        if item_count:
            blockers["StorageMovementItem path snapshots"] = (
                item_count
            )

    return {
        "root_id": root.pk,
        "root_path": root.full_path,
        "workspace_id": root.workspace_id,
        "ids": ids,
        "location_count": len(ids),
        "descendant_count": len(ids) - 1,
        "sample_count": sample_count,
        "assignment_count": assignment_count,
        "textual_count": textual_count,
        "blockers": blockers,
        "can_delete": not (
            assignment_count
            or textual_count
            or blockers
        ),
    }


def preview_empty_storage_subtree(*, actor, location_id):
    """Read-only preview, restricted to an authorized manager."""
    result = _analyze(actor, location_id)

    return {
        key: value
        for key, value in result.items()
        if key not in {"ids"}
    }


@transaction.atomic
def delete_empty_storage_subtree(
    *,
    actor,
    location_id,
    confirmation,
):
    """Delete an unreferenced subtree, atomically and with audit."""

    if confirmation != "DELETE":
        raise ValidationError(
            "Explicit deletion confirmation is required."
        )

    from core.services.storage_writer_lock import (
        acquire_storage_writer_lock,
    )

    acquire_storage_writer_lock()

    result = _analyze(actor, location_id, lock=True)

    if result["assignment_count"] or result["textual_count"]:
        raise ValidationError(
            "This location or one of its descendants is linked "
            "to Samples. Transfer or reconcile the Samples "
            "before deleting the storage hierarchy."
        )

    if result["blockers"]:
        raise ValidationError(
            "The storage hierarchy has references in other "
            "records or movement history and cannot be "
            "permanently deleted."
        )

    # Keep a durable deletion audit without introducing
    # a migration or misusing a Sample movement event.
    if not apps.is_installed("django.contrib.admin"):
        raise ValidationError(
            "The deletion audit facility is not configured."
        )

    from django.contrib.admin.models import (
        DELETION,
        LogEntry,
    )
    from django.contrib.contenttypes.models import ContentType

    LogEntry.objects.create(
        user_id=actor.pk,
        content_type=ContentType.objects.get_for_model(
            StorageLocation
        ),
        object_id=str(result["root_id"]),
        object_repr=result["root_path"][:200],
        action_flag=DELETION,
        change_message=json.dumps({
            "operation": "delete_empty_storage_subtree",
            "path": result["root_path"],
            "location_ids": result["ids"],
            "location_count": result["location_count"],
        }),
    )

    count, _ = StorageLocation.objects.filter(
        pk__in=result["ids"]
    ).delete()

    if count != result["location_count"]:
        raise ValidationError(
            "Unexpected dependent deletion; transaction reverted."
        )

    return result
