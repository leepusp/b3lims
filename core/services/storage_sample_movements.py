"""Audited movement of selected SampleStorageAssignment rows."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageMovementItem,
)
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
)
from core.permissions.storage_movements_v8 import (
    authorize_sample_storage_move_v8,
)
from core.services.storage_legacy_sync import (
    sync_primary_storage_legacy_for_samples,
)

MAX_BULK_ASSIGNMENTS = 500


def _ancestors(location_id):
    """Return node and ancestor IDs; reject cycles."""
    ids = set()
    current = location_id

    while current is not None:
        if current in ids:
            raise ValidationError("Cyclic storage hierarchy.")

        ids.add(current)
        current = StorageLocation.objects.values_list(
            "parent_id", flat=True
        ).get(pk=current)

    return ids


def _normalize_moves(moves):
    requests = list(moves)

    if not requests or len(requests) > MAX_BULK_ASSIGNMENTS:
        raise ValidationError(
            "Select between 1 and 500 assignments."
        )

    seen_ids = set()

    for item in requests:
        if not isinstance(item, dict):
            raise ValidationError("Invalid movement entry.")

        required = (
            "assignment_id",
            "destination_id",
            "position",
            "expected_location_id",
            "expected_position",
            "expected_source_path",
            "expected_destination_path",
        )

        if any(key not in item for key in required):
            raise ValidationError(
                "Movement entry is missing a required field."
            )

        for key in (
            "assignment_id",
            "destination_id",
            "expected_location_id",
        ):
            if type(item[key]) is not int or item[key] < 1:
                raise ValidationError(f"Invalid {key}.")

        for key in (
            "position",
            "expected_position",
            "expected_source_path",
            "expected_destination_path",
        ):
            if not isinstance(item[key], str):
                raise ValidationError(f"Invalid {key}.")

        if len(item["position"].strip()) > 100:
            raise ValidationError(
                "Position exceeds 100 characters."
            )

        if item["assignment_id"] in seen_ids:
            raise ValidationError(
                "An assignment was selected more than once."
            )

        seen_ids.add(item["assignment_id"])

    return requests


def _execute_movement(
    *,
    moves,
    actor,
    reason,
    movement_type,
):
    if not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")

    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A movement reason is required.")

    requests = _normalize_moves(moves)
    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()
    ids = sorted(item["assignment_id"] for item in requests)

    lookup = {
        item["assignment_id"]: item
        for item in requests
    }

    # Discover the location locks before modifying any data.
    original_locations = dict(
        SampleStorageAssignment.objects
        .filter(pk__in=ids)
        .values_list("pk", "location_id")
    )

    if len(original_locations) != len(ids):
        raise ValidationError(
            "One or more assignments no longer exist."
        )

    lock_ids = set()

    for item in requests:
        assignment_id = item["assignment_id"]

        lock_ids.update(
            _ancestors(original_locations[assignment_id])
        )
        lock_ids.update(
            _ancestors(item["destination_id"])
        )

    # Cooperating movements serialize on source/destination
    # infrastructure rows, including their ancestors.
    list(
        StorageLocation.objects
        .select_for_update()
        .filter(pk__in=lock_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    for item in requests:
        current_ids = (
            _ancestors(original_locations[item["assignment_id"]])
            | _ancestors(item["destination_id"])
        )

        if not current_ids.issubset(lock_ids):
            raise ValidationError(
                "The storage hierarchy changed. Retry."
            )

    assignments = list(
        SampleStorageAssignment.objects
        .select_for_update()
        .filter(pk__in=ids)
        .order_by("pk")
    )

    if len(assignments) != len(ids):
        raise ValidationError(
            "One or more assignments no longer exist."
        )

    # The source may have changed between initial discovery and
    # acquiring the assignment row locks. Never proceed using
    # an unlocked source or ancestor.
    for assignment in assignments:
        current_source_ancestors = _ancestors(
            assignment.location_id
        )

        if not current_source_ancestors.issubset(lock_ids):
            raise ValidationError(
                "Source location changed during lock acquisition. "
                "Retry."
            )

    sample_ids = sorted({
        assignment.sample_id
        for assignment in assignments
    })

    samples = {
        sample.pk: sample
        for sample in (
            Sample.objects
            .select_for_update()
            .filter(pk__in=sample_ids)
            .order_by("pk")
        )
    }

    # Every selected Sample must be editable by this actor.
    for sample_id in sample_ids:
        sample = samples.get(sample_id)

        if sample is None or not can_operate_on_sample_storage(actor, sample):
            raise PermissionDenied(
                "Permission to move this Sample is required."
            )

    final_slots = set()
    snapshots = []

    for assignment in assignments:
        item = lookup[assignment.pk]

        destination = StorageLocation.objects.get(
            pk=item["destination_id"]
        )
        origin = StorageLocation.objects.get(
            pk=assignment.location_id
        )

        old_path = origin.full_path
        new_path = destination.full_path

        if (
            assignment.status != "active"
            or assignment.location_id
            != item["expected_location_id"]
            or assignment.position
            != item["expected_position"]
            or old_path != item["expected_source_path"]
            or new_path != item["expected_destination_path"]
        ):
            raise ValidationError(
                "Storage changed since the request was prepared."
            )

        # Authorization must be checked after the row locks
        # have been acquired and before any assignment is updated.
        authorize_sample_storage_move_v8(
            actor=actor,
            assignment=assignment,
            destination=destination,
        )

        # A Sample can leave an inactive origin; it cannot be
        # moved into an inactive destination.
        if StorageLocation.objects.filter(
            pk__in=_ancestors(destination.pk),
            is_active=False,
        ).exists():
            raise ValidationError(
                "The destination hierarchy is inactive."
            )

        final_position = item["position"].strip()

        if (
            assignment.location_id == destination.pk
            and assignment.position == final_position
        ):
            raise ValidationError(
                "Movement contains an unchanged assignment."
            )

        if final_position:
            slot = (
                destination.pk,
                final_position.casefold(),
            )

            if slot in final_slots:
                raise ValidationError(
                    "Two selected assignments target the same slot."
                )

            final_slots.add(slot)

        snapshots.append({
            "assignment": assignment,
            "sample": samples[assignment.sample_id],
            "origin_id": assignment.location_id,
            "destination_id": destination.pk,
            "old_position": assignment.position,
            "new_position": final_position,
            "old_path": old_path,
            "new_path": new_path,
        })

    # Positions occupied by selected assignments may be reused
    # within the same batch, allowing atomic position swaps.
    destination_ids = {
        entry[0]
        for entry in final_slots
    }

    if destination_ids:
        occupied = (
            SampleStorageAssignment.objects
            .filter(
                status="active",
                location_id__in=destination_ids,
            )
            .exclude(pk__in=ids)
            .exclude(position="")
            .values_list("location_id", "position")
        )

        for location_id, position in occupied:
            if (
                location_id,
                position.strip().casefold(),
            ) in final_slots:
                raise ValidationError(
                    "Destination position is occupied."
                )

    now = timezone.now()

    # Phase 1: release the occupied positions for all
    # selected assignments inside this transaction.
    #
    # The unique_active_storage_slot_v8 constraint excludes
    # blank positions. This allows P01 <-> P03 swaps without
    # temporarily violating the immediate unique index.
    #
    # A failure anywhere below rolls back both phases.
    SampleStorageAssignment.objects.filter(
        pk__in=ids
    ).update(
        position="",
        updated_at=now,
    )

    # Phase 2: write every authorized final destination.
    # IDs, ranks, quantities and canonical assignment
    # identities remain unchanged.
    for entry in snapshots:
        SampleStorageAssignment.objects.filter(
            pk=entry["assignment"].pk
        ).update(
            location_id=entry["destination_id"],
            position=entry["new_position"],
            updated_at=now,
        )

    # Synchronize Sample's primary legacy representation.
    sync_primary_storage_legacy_for_samples(
        sample_ids=sample_ids
    )

    source_ids = {
        entry["origin_id"]
        for entry in snapshots
    }
    target_ids = {
        entry["destination_id"]
        for entry in snapshots
    }
    source_paths = {
        entry["old_path"]
        for entry in snapshots
    }
    target_paths = {
        entry["new_path"]
        for entry in snapshots
    }

    movement = StorageMovement.objects.create(
        movement_type=movement_type,
        origin_location_id=(
            next(iter(source_ids))
            if len(source_ids) == 1 else None
        ),
        destination_location_id=(
            next(iter(target_ids))
            if len(target_ids) == 1 else None
        ),
        origin_path=(
            next(iter(source_paths))
            if len(source_paths) == 1 else ""
        ),
        destination_path=(
            next(iter(target_paths))
            if len(target_paths) == 1 else ""
        ),
        affected_location_count=0,
        affected_sample_count=len(sample_ids),
        affected_assignment_count=len(snapshots),
        performed_by=actor,
        actor_label=actor.get_username()[:255],
        reason=reason.strip(),
    )

    StorageMovementItem.objects.bulk_create([
        StorageMovementItem(
            movement=movement,
            sample_id=entry["sample"].pk,
            sample_identifier=entry["sample"].sample_id,
            assignment_id_snapshot=entry["assignment"].pk,
            location_id_snapshot=entry["origin_id"],
            destination_location_id_snapshot=entry["destination_id"],
            position_before=entry["old_position"],
            position_after=entry["new_position"],
            path_before=entry["old_path"],
            path_after=entry["new_path"],
        )
        for entry in snapshots
    ])

    return movement


@transaction.atomic
def move_sample(
    *,
    assignment_id,
    destination_id,
    position,
    expected_location_id,
    expected_position,
    expected_source_path,
    expected_destination_path,
    actor,
    reason,
):
    """Move one assignment, retaining all other assignments."""
    return _execute_movement(
        moves=[{
            "assignment_id": assignment_id,
            "destination_id": destination_id,
            "position": position,
            "expected_location_id": expected_location_id,
            "expected_position": expected_position,
            "expected_source_path": expected_source_path,
            "expected_destination_path": expected_destination_path,
        }],
        actor=actor,
        reason=reason,
        movement_type="sample",
    )


@transaction.atomic
def move_samples_bulk(*, moves, actor, reason):
    """Move selected assignments atomically."""
    return _execute_movement(
        moves=moves,
        actor=actor,
        reason=reason,
        movement_type="sample_bulk",
    )
