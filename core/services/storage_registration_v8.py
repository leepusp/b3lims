"""Audited initial physical assignment without representing a transfer."""

import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from core.services.storage_position_names_v8146c2 import normalize_physical_position_v8146c2

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageMovementItem,
)
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
    can_register_at_storage_location,
    can_view_storage_location,
    is_storage_global_admin,
)
from core.services.storage_locations import _sync_legacy_storage_levels
from core.services.storage_writer_lock import acquire_storage_writer_lock


@transaction.atomic
def register_initial_physical_storage(
    *,
    sample,
    box,
    position,
    actor,
    mode,
    expected_legacy_path,
    reason="",
):
    """
    Register a physical position without moving the Sample.

    mode="new": newly created, unassigned Sample.
    mode="historical": reconcile a verified historical location.

    This function does not create StorageLocation records.
    """
    if actor is None or not actor.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    if mode not in {"new", "historical"}:
        raise ValidationError("Invalid registration mode.")

    if mode == "historical":
        if not is_storage_global_admin(actor):
            raise PermissionDenied(
                "Historical reconciliation requires infrastructure permission."
            )

    acquire_storage_writer_lock()

    sample = Sample.objects.select_for_update().get(pk=sample.pk)
    box = StorageLocation.objects.select_for_update().get(pk=box.pk)

    if not can_operate_on_sample_storage(actor, sample):
        raise PermissionDenied(
            "You cannot register storage for this Sample."
        )

    # Check scope before exposing the physical state.
    if not can_view_storage_location(actor, box):
        raise PermissionDenied(
            "You cannot register storage at this location."
        )

    position = normalize_physical_position_v8146c2(position)

    if box.location_type not in {"box", "rack", "other"}:
        raise ValidationError(
            "Select a Box, Rack, or user-defined storage destination."
        )

    node = box
    visited = set()

    while node is not None:
        if node.pk in visited:
            raise ValidationError("Cyclic storage hierarchy.")

        visited.add(node.pk)

        if not node.is_active:
            raise ValidationError(
                "The Box and all its parents must be active."
            )

        node = node.parent

    # The active-state validation above is a domain check.
    # Recheck full operational access before writing.
    if not can_register_at_storage_location(actor, box):
        raise PermissionDenied(
            "You cannot register storage at this location."
        )

    parts = [*box.full_path_parts, position]
    canonical_path = " > ".join(parts)

    if len(canonical_path) > 255:
        raise ValidationError("Storage path exceeds 255 characters.")

    if any(len(part) > 150 for part in parts):
        raise ValidationError("Storage level exceeds 150 characters.")

    previous_path = (sample.storage_location or "").strip()
    expected = (expected_legacy_path or "").strip()

    if previous_path != expected:
        raise ValidationError(
            "Storage changed since preview. Reload and review."
        )

    if mode == "new" and previous_path:
        raise ValidationError(
            "New physical registration requires an unassigned Sample."
        )

    if mode == "historical" and previous_path != canonical_path:
        raise ValidationError(
            "Historical path does not match the confirmed physical position."
        )

    existing = list(
        SampleStorageAssignment.objects
        .select_for_update()
        .filter(sample=sample)
    )

    if existing:
        if (
            len(existing) == 1
            and existing[0].status == "active"
            and existing[0].location_id == box.pk
            and existing[0].position == position
            and previous_path == canonical_path
        ):
            # Safe retry: no second registration or audit entry.
            return existing[0], None

        raise ValidationError(
            "Sample already has physical assignments."
        )

    if (
        SampleStorageAssignment.objects
        .filter(
            location=box,
            position__iexact=position,
            status="active",
        )
        .exists()
    ):
        raise ValidationError(
            "This position is already occupied."
        )

    assignment = SampleStorageAssignment.objects.create(
        sample=sample,
        location=box,
        rank=1,
        is_primary=True,
        position=position,
        status="active",
    )

    Sample.objects.filter(pk=sample.pk).update(
        storage_location=canonical_path
    )

    _sync_legacy_storage_levels(sample, parts)

    audit_reason = (
        reason.strip()
        if isinstance(reason, str) and reason.strip()
        else (
            "Verified historical physical registration; no movement."
            if mode == "historical"
            else "Initial physical storage registration; no movement."
        )
    )

    movement = StorageMovement.objects.create(
        movement_type="registration",
        destination_location=box,
        origin_path=previous_path,
        destination_path=canonical_path,
        affected_location_count=0,
        affected_sample_count=1,
        affected_assignment_count=1,
        performed_by=actor,
        actor_label=actor.get_username(),
        reason=audit_reason,
    )

    StorageMovementItem.objects.create(
        movement=movement,
        sample=sample,
        sample_identifier=sample.sample_id,
        assignment_id_snapshot=assignment.pk,
        location_id_snapshot=box.pk,
        destination_location_id_snapshot=box.pk,
        position_before="",
        position_after=position,
        path_before=previous_path,
        path_after=canonical_path,
    )

    return assignment, movement
