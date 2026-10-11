"""Read-only, permission-scoped preview of selected Sample transfers."""

from django.core.exceptions import PermissionDenied, ValidationError

from core.models.samples.storage import SampleStorageAssignment, StorageLocation
from core.permissions.samples import can_edit_sample

MAX_PREVIEW_ASSIGNMENTS = 50


def _check_active_hierarchy(location):
    seen = set()
    node = location

    while node is not None:
        if node.pk in seen:
            raise ValidationError("Cyclic storage hierarchy.")

        seen.add(node.pk)

        if not node.is_active:
            raise ValidationError(
                "Source or destination hierarchy is inactive."
            )

        node = (
            StorageLocation.objects.get(pk=node.parent_id)
            if node.parent_id is not None
            else None
        )


def preview_sample_movements(*, moves, actor):
    """
    Read-only preview of selected assignment transfers.

    Each request has:
      assignment_id: int
      destination_id: int
      position: str

    The preview is advisory. Execution must revalidate DB state.
    """
    if not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")

    requested = list(moves)

    if not 1 <= len(requested) <= MAX_PREVIEW_ASSIGNMENTS:
        raise ValidationError("Select between 1 and 50 assignments.")

    selected_ids = set()
    destination_ids = set()

    for entry in requested:
        if not isinstance(entry, dict):
            raise ValidationError("Invalid transfer request.")

        aid = entry.get("assignment_id")
        did = entry.get("destination_id")
        position = entry.get("position")

        if (
            type(aid) is not int
            or aid < 1
            or type(did) is not int
            or did < 1
            or not isinstance(position, str)
            or len(position.strip()) > 100
        ):
            raise ValidationError("Invalid transfer fields.")

        if aid in selected_ids:
            raise ValidationError(
                "An assignment was selected twice."
            )

        selected_ids.add(aid)
        destination_ids.add(did)

    assignments = {
        obj.pk: obj
        for obj in (
            SampleStorageAssignment.objects
            .select_related("sample", "location")
            .filter(pk__in=selected_ids)
        )
    }

    destinations = StorageLocation.objects.in_bulk(destination_ids)

    if (
        len(assignments) != len(selected_ids)
        or len(destinations) != len(destination_ids)
    ):
        raise ValidationError(
            "One or more selected records no longer exist."
        )

    rows = []
    slots = set()
    sample_destinations = set()

    for entry in requested:
        assignment = assignments[entry["assignment_id"]]
        destination = destinations[entry["destination_id"]]
        position = entry["position"].strip()
        sample = assignment.sample

        if not sample.is_active or not can_edit_sample(actor, sample):
            raise PermissionDenied(
                "Permission to move this Sample is required."
            )

        if assignment.status != "active":
            raise ValidationError(
                "Selected assignment is not active."
            )

        _check_active_hierarchy(assignment.location)
        _check_active_hierarchy(destination)

        if (
            assignment.location_id == destination.pk
            and assignment.position == position
        ):
            raise ValidationError(
                "No location or position change was requested."
            )

        sample_destination = (sample.pk, destination.pk)

        if sample_destination in sample_destinations:
            raise ValidationError(
                "Duplicate Sample destination in this batch."
            )

        sample_destinations.add(sample_destination)

        if (
            SampleStorageAssignment.objects
            .filter(
                sample_id=sample.pk,
                location_id=destination.pk,
                status="active",
            )
            .exclude(pk__in=selected_ids)
            .exists()
        ):
            raise ValidationError(
                "Sample already has an assignment at this destination."
            )

        if position:
            slot = (destination.pk, position.casefold())

            if slot in slots:
                raise ValidationError(
                    "Multiple transfers target the same position."
                )

            slots.add(slot)

        if (
            assignment.rank == 1
            and len(destination.full_path) > 255
        ):
            raise ValidationError(
                "Primary storage path exceeds the legacy field limit."
            )

        rows.append({
            "assignment_id": assignment.pk,
            "sample_identifier": sample.sample_id,
            "origin_path": assignment.location.full_path,
            "destination_id": destination.pk,
            "destination_path": destination.full_path,
            "position_before": assignment.position,
            "position_after": position,
            "expected_location_id": assignment.location_id,
            "expected_position": assignment.position,
            "expected_source_path": assignment.location.full_path,
            "expected_destination_path": destination.full_path,
        })

    if slots:
        occupied = (
            SampleStorageAssignment.objects
            .filter(
                status="active",
                location_id__in={
                    slot[0] for slot in slots
                },
            )
            .exclude(pk__in=selected_ids)
            .exclude(position="")
            .values_list("location_id", "position")
        )

        if any(
            (location_id, value.strip().casefold()) in slots
            for location_id, value in occupied
        ):
            raise ValidationError(
                "Destination position is occupied."
            )

    return {
        "preview_only": True,
        "affected_assignment_count": len(rows),
        "affected_sample_count": len({
            assignments[row["assignment_id"]].sample_id
            for row in rows
        }),
        "moves": rows,
    }
