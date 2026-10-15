"""Reconcile existing Sample storage without replacing unchanged rows."""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.services.storage_locations import (
    split_location_text,
    _get_or_create_location_path,
    _sync_legacy_storage_levels,
)
from core.services.storage_legacy_sync import (
    sync_primary_storage_legacy_for_samples,
)


class StorageMetadataProtectionError(ValidationError):
    """An edit would discard unaudited physical metadata."""



@transaction.atomic
def reconcile_sample_storage_from_text(
    *,
    sample,
    storage_location_text,
    actor=None,
    reason="",
):
    """
    Reconcile requested active paths while preserving assignment IDs.

    Unchanged assignments retain their physical positions and metadata.
    An assignment moved to another location has its old slot cleared.
    Inactive assignments are not deleted.
    """
    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()
    sample = Sample.objects.select_for_update().get(pk=sample.pk)

    requested = split_location_text(storage_location_text or "")
    destinations = []

    for levels in requested:
        location = _get_or_create_location_path(levels)

        if not isinstance(location, StorageLocation):
            raise ValidationError("Invalid storage destination.")

        node = location
        visited = set()

        while node is not None:
            if node.pk in visited:
                raise ValidationError("Cyclic storage hierarchy.")

            visited.add(node.pk)

            if not node.is_active:
                raise ValidationError(
                    "Cannot assign a Sample to an inactive location."
                )

            node = node.parent

        destinations.append(location)

    existing = list(
        SampleStorageAssignment.objects
        .select_for_update()
        .filter(sample=sample)
        .order_by("rank", "pk")
    )

    # Preserve the original physical state before reconciliation.
    previous_assignments = {
        assignment.pk: {
            "location_id": assignment.location_id,
            "path": assignment.location.full_path,
            "position": assignment.position,
            "rank": assignment.rank,
            "is_primary": assignment.is_primary,
            "status": assignment.status,
        }
        for assignment in existing
    }

    active = [
        assignment for assignment in existing
        if assignment.status == "active"
    ]

    inactive_ranks = {
        assignment.rank for assignment in existing
        if assignment.status != "active"
    }

    requested_ranks = set(range(1, len(destinations) + 1))

    if requested_ranks & inactive_ranks:
        raise ValidationError(
            "Inactive assignment ranks conflict with this edit. "
            "Resolve the inactive assignments before reordering."
        )

    # First match exact locations. This preserves secondary rows
    # even when another path changes.
    available = {assignment.pk: assignment for assignment in active}
    matched = [None] * len(destinations)

    for index, location in enumerate(destinations):
        for assignment in active:
            if (
                assignment.pk in available
                and assignment.location_id == location.pk
            ):
                matched[index] = assignment
                del available[assignment.pk]
                break

    # Reuse unmatched assignments for genuinely changed paths.
    for index in range(len(destinations)):
        if matched[index] is not None:
            continue

        preferred_rank = index + 1

        assignment = next(
            (
                item for item in available.values()
                if item.rank == preferred_rank
            ),
            None,
        )

        if assignment is None:
            assignment = next(iter(available.values()), None)

        if assignment is not None:
            matched[index] = assignment
            del available[assignment.pk]

    # Temporarily free active ranks to support reordering without
    # violating the unique constraint (sample, rank).
    temporary_start = max(
        (assignment.rank for assignment in existing),
        default=0,
    ) + 1

    for offset, assignment in enumerate(active):
        SampleStorageAssignment.objects.filter(
            pk=assignment.pk
        ).update(rank=temporary_start + offset)

    # Positions are already preserved in movement history.
    # Other physical metadata cannot be discarded by text editing.
    pending_removals = list(available.values())

    for assignment in pending_removals:
        if (
            bool((assignment.container_type or "").strip())
            or assignment.quantity is not None
            or bool((assignment.quantity_unit or "").strip())
            or bool((assignment.notes or "").strip())
        ):
            raise StorageMetadataProtectionError(
                "An assignment with physical metadata cannot be "
                "removed through text editing. Use a controlled "
                "storage operation."
            )

    for assignment in pending_removals:
        assignment.delete()

    for index, (location, assignment) in enumerate(
        zip(destinations, matched),
        start=1,
    ):
        if assignment is None:
            SampleStorageAssignment.objects.create(
                sample=sample,
                location=location,
                rank=index,
                is_primary=(index == 1),
                status="active",
            )
            continue

        changes = {
            "location_id": location.pk,
            "rank": index,
            "is_primary": index == 1,
        }

        # An old position is not automatically valid in a new box.
        if assignment.location_id != location.pk:
            changes["position"] = ""

        SampleStorageAssignment.objects.filter(
            pk=assignment.pk
        ).update(**changes)

    if destinations:
        sync_primary_storage_legacy_for_samples(
            sample_ids={sample.pk},
        )
    else:
        Sample.objects.filter(pk=sample.pk).update(
            storage_location=""
        )
        _sync_legacy_storage_levels(sample, [])


    # Audit all effective assignment changes in the same transaction.
    from core.models.samples.storage import (
        StorageMovement,
        StorageMovementItem,
    )

    updated_assignments = list(
        SampleStorageAssignment.objects
        .select_related("location")
        .filter(sample=sample)
        .order_by("pk")
    )

    current_assignments = {
        assignment.pk: {
            "location_id": assignment.location_id,
            "path": assignment.location.full_path,
            "position": assignment.position,
            "rank": assignment.rank,
            "is_primary": assignment.is_primary,
            "status": assignment.status,
        }
        for assignment in updated_assignments
    }

    changed = [
        (
            assignment_id,
            previous_assignments.get(assignment_id),
            current_assignments.get(assignment_id),
        )
        for assignment_id in sorted(
            set(previous_assignments) | set(current_assignments)
        )
        if (
            previous_assignments.get(assignment_id)
            != current_assignments.get(assignment_id)
        )
    ]

    if changed:
        source_ids = {
            before["location_id"]
            for _, before, _ in changed
            if before is not None
        }
        destination_ids = {
            after["location_id"]
            for _, _, after in changed
            if after is not None
        }
        source_paths = {
            before["path"]
            for _, before, _ in changed
            if before is not None
        }
        destination_paths = {
            after["path"]
            for _, _, after in changed
            if after is not None
        }

        identified_actor = (
            actor
            if actor is not None
            and getattr(actor, "is_authenticated", False)
            else None
        )

        movement = StorageMovement.objects.create(
            movement_type="sample",
            origin_location_id=(
                next(iter(source_ids))
                if len(source_ids) == 1 else None
            ),
            destination_location_id=(
                next(iter(destination_ids))
                if len(destination_ids) == 1 else None
            ),
            origin_path=(
                next(iter(source_paths))
                if len(source_paths) == 1 else ""
            ),
            destination_path=(
                next(iter(destination_paths))
                if len(destination_paths) == 1 else ""
            ),
            affected_location_count=0,
            affected_sample_count=1,
            affected_assignment_count=len(changed),
            performed_by=identified_actor,
            actor_label=(
                identified_actor.get_username()[:255]
                if identified_actor is not None
                else "System (unattributed)"
            ),
            reason=(
                (reason or "").strip()
                or "Internal storage reconciliation; actor not supplied."
            ),
        )

        StorageMovementItem.objects.bulk_create([
            StorageMovementItem(
                movement=movement,
                sample=sample,
                destination_location_id_snapshot=(
                    after["location_id"]
                    if after is not None
                    else None
                ),
                sample_identifier=sample.sample_id,
                assignment_id_snapshot=assignment_id,
                location_id_snapshot=(
                    before["location_id"]
                    if before is not None
                    else after["location_id"]
                ),
                position_before=(
                    before["position"] if before is not None else ""
                ),
                position_after=(
                    after["position"] if after is not None else ""
                ),
                path_before=(
                    before["path"] if before is not None else ""
                ),
                path_after=(
                    after["path"] if after is not None else ""
                ),
            )
            for assignment_id, before, after in changed
        ])
    return len(destinations)
