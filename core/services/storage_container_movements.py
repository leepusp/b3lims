"""Transactional container movement with persistent audit."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageMovementItem,
)
from core.permissions.storage import can_manage_storage_infrastructure
from core.services.storage_legacy_sync import (
    sync_primary_storage_legacy_for_samples,
)
from core.services.storage_movement_preview import (
    _ancestor_ids,
    _descendant_ids,
    preview_storage_container_move,
)


@transaction.atomic
def move_storage_container(
    *,
    container,
    destination,
    actor,
    expected_parent_id,
    reason,
    expected_origin_path=None,
    expected_destination_path=None,
):
    """
    Move a container without modifying SampleStorageAssignment.

    Internal C1 implementation. Do not expose through views until
    legacy synchronization and integration tests are complete.
    """
    if not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication is required.")

    if not can_manage_storage_infrastructure(actor):
        raise PermissionDenied("Storage management permission required.")

    if not reason or not reason.strip():
        raise ValidationError("A movement reason is required.")

    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()
    container = StorageLocation.objects.get(pk=container.pk)
    destination = StorageLocation.objects.get(pk=destination.pk)

    if container.location_type in {"room", "position"}:
        raise ValidationError(
            "Only movable storage infrastructure is supported."
        )

    if destination.location_type == "position":
        raise ValidationError(
            "A position cannot receive a storage container."
        )

    descendants_before = _descendant_ids(container)
    source_ancestors = _ancestor_ids(container)
    destination_ancestors = _ancestor_ids(destination)

    lock_ids = (
        descendants_before
        | source_ancestors
        | destination_ancestors
    )

    # Lock in a deterministic order to reduce conflicting updates.
    list(
        StorageLocation.objects
        .select_for_update()
        .filter(pk__in=lock_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    container.refresh_from_db()
    destination.refresh_from_db()

    if (
        expected_origin_path is not None
        and container.full_path != expected_origin_path
    ):
        raise ValidationError("The container source path has changed since preview.")

    if (
        expected_destination_path is not None
        and f"{destination.full_path} > {container.name}" != expected_destination_path
    ):
        raise ValidationError("The container destination path has changed since preview.")

    if container.parent_id != expected_parent_id:
        raise ValidationError(
            "The container has moved since this request was prepared."
        )

    if _descendant_ids(container) != descendants_before:
        raise ValidationError(
            "The container hierarchy changed during validation."
        )

    ancestors = (
        _ancestor_ids(container)
        | _ancestor_ids(destination)
    )

    if StorageLocation.objects.filter(
        pk__in=ancestors,
        is_active=False,
    ).exists():
        raise ValidationError(
            "The source and destination hierarchy must be active."
        )

    preview = preview_storage_container_move(
        container=container,
        destination=destination,
    )

    affected_ids = _descendant_ids(container)

    assignments = list(
        SampleStorageAssignment.objects
        .select_for_update()
        .select_related("sample", "location")
        .filter(
            location_id__in=affected_ids,
            status="active",
        )
        .order_by("pk")
    )

    snapshot = [
        {
            "sample_id": assignment.sample_id,
            "sample_identifier": assignment.sample.sample_id,
            "assignment_id": assignment.pk,
            "location_id": assignment.location_id,
            "position": assignment.position,
            "path_before": assignment.location.full_path,
        }
        for assignment in assignments
    ]

    origin_parent_id = container.parent_id
    origin_path = container.full_path

    # Moving the node changes paths without changing assignments.
    container.parent = destination
    container.save(update_fields=["parent"])

    container.refresh_from_db()
    destination_path = container.full_path

    # Refresh the legacy primary path for every affected Sample.
    # This is part of the same transaction as the container move.
    # Canonical assignment IDs and positions are preserved.
    sync_primary_storage_legacy_for_samples(
        sample_ids={
            entry["sample_id"]
            for entry in snapshot
        },
    )

    movement = StorageMovement.objects.create(
        movement_type="container",
        moved_location=container,
        origin_location_id=origin_parent_id,
        destination_location=destination,
        origin_path=origin_path,
        destination_path=destination_path,
        affected_location_count=preview[
            "affected_location_count"
        ],
        affected_sample_count=preview[
            "active_sample_count"
        ],
        affected_assignment_count=len(snapshot),
        performed_by=actor,
        actor_label=actor.get_username()[:255],
        reason=reason.strip(),
    )

    new_paths = {
        location_id: StorageLocation.objects.get(
            pk=location_id
        ).full_path
        for location_id in {
            entry["location_id"] for entry in snapshot
        }
    }

    StorageMovementItem.objects.bulk_create([
        StorageMovementItem(
            movement=movement,
            sample_id=entry["sample_id"],
            sample_identifier=entry["sample_identifier"],
            assignment_id_snapshot=entry["assignment_id"],
            location_id_snapshot=entry["location_id"],
            position_before=entry["position"],
            position_after=entry["position"],
            path_before=entry["path_before"],
            path_after=new_paths[entry["location_id"]],
        )
        for entry in snapshot
    ])

    return movement
