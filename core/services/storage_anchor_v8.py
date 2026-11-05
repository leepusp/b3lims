"""Validate registered storage anchors for new Sample registration."""

import re
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from core.services.storage_layout_position import position_for_layout
from core.services.storage_position_names_v8146c2 import normalize_physical_position_v8146c2

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)


@dataclass(frozen=True)
class StorageAnchorPlan:
    box_id: int | None
    box_path: str
    positions: tuple[str, ...]


def validate_storage_anchor_plan(
    *,
    mode,
    box_id,
    positions,
    expected_samples,
    actor=None,
):
    """
    Validate proposed physical assignments without writing data.

    This is a preview validator, not the final transaction check.
    Authorization and occupancy must be rechecked during saving.
    """
    if not isinstance(expected_samples, int) or expected_samples < 1:
        raise ValidationError("Invalid Sample count.")

    if mode == "unassigned":
        if box_id not in (None, "") or any(positions):
            raise ValidationError(
                "Unassigned registration must not specify physical storage."
            )

        return StorageAnchorPlan(None, "", ())

    if mode != "physical":
        raise ValidationError("Invalid storage registration mode.")

    try:
        pk = int(box_id)
    except (TypeError, ValueError):
        raise ValidationError("Select a registered Box.")

    if pk <= 0:
        raise ValidationError("Select a registered Box.")

    box = StorageLocation.objects.filter(pk=pk).first()

    if box is None or box.location_type == "position":
        raise ValidationError("Select a registered physical storage location.")

    if actor is not None:
        from core.permissions.storage_workspaces_v8 import (
            can_register_at_storage_location,
            can_view_storage_location,
        )

        if not can_view_storage_location(actor, box):
            raise PermissionDenied(
                "Physical storage destination is not accessible."
            )

    visited = set()
    node = box

    while node is not None:
        if node.pk in visited:
            raise ValidationError("Cyclic storage hierarchy.")

        visited.add(node.pk)

        if not node.is_active:
            raise ValidationError(
                "The Box and all parent locations must be active."
            )

        node = node.parent

    # Authorized users receive a specific ValidationError for
    # inactive equipment. Foreign users remain denied earlier.
    if actor is not None and not can_register_at_storage_location(
        actor, box
    ):
        raise PermissionDenied(
            "Physical storage destination is not accessible."
        )

    normalized = tuple(
        position_for_layout(
            box, normalize_physical_position_v8146c2(value)
        )
        for value in positions
    )

    if len(normalized) != expected_samples:
        raise ValidationError(
            "Provide one position for every Sample being created."
        )

    if len({value.casefold() for value in normalized}) != len(normalized):
        raise ValidationError(
            "Two new Samples cannot use the same Box position."
        )

    for position in normalized:
        if SampleStorageAssignment.objects.filter(
            location=box,
            status="active",
            position__iexact=position,
        ).exists():
            raise ValidationError(
                f"Position {position} is already occupied."
            )

    return StorageAnchorPlan(
        box_id=box.pk,
        box_path=box.full_path,
        positions=normalized,
    )
