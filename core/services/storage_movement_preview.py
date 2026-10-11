"""Read-only validation for hierarchical storage movements."""

from django.core.exceptions import ValidationError

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)


def _ancestor_ids(location):
    """Return ancestor IDs, rejecting malformed cyclic hierarchies."""
    seen = set()
    node = location

    while node is not None:
        if node.pk in seen:
            raise ValidationError(
                "A cycle was detected in the storage hierarchy."
            )

        seen.add(node.pk)

        node = (
            StorageLocation.objects.get(pk=node.parent_id)
            if node.parent_id
            else None
        )

    return seen


def _descendant_ids(location):
    """Return the location and all of its descendants."""
    found = {location.pk}
    frontier = [location.pk]

    while frontier:
        children = list(
            StorageLocation.objects.filter(
                parent_id__in=frontier
            ).values_list("pk", flat=True)
        )

        if any(pk in found for pk in children):
            raise ValidationError(
                "A cycle was detected in the storage hierarchy."
            )

        found.update(children)
        frontier = children

    return found


def preview_storage_container_move(*, container, destination):
    """
    Validate movement without changing storage records.

    This function does not authorize or execute a transfer.
    """
    container = StorageLocation.objects.get(pk=container.pk)
    destination = StorageLocation.objects.get(pk=destination.pk)

    if not container.is_active:
        raise ValidationError("The container is inactive.")

    if not destination.is_active:
        raise ValidationError("The destination is inactive.")

    if container.location_type in {"room", "position"}:
        raise ValidationError(
            "Rooms and individual positions cannot be moved as containers."
        )

    if destination.location_type == "position":
        raise ValidationError(
            "A position cannot be a container destination."
        )

    if container.pk == destination.pk:
        raise ValidationError(
            "A container cannot contain itself."
        )

    if container.parent_id == destination.pk:
        raise ValidationError(
            "The container is already at this destination."
        )

    container_ancestors = _ancestor_ids(container)
    destination_ancestors = _ancestor_ids(destination)

    if StorageLocation.objects.filter(
        pk__in=(container_ancestors | destination_ancestors),
        is_active=False,
    ).exists():
        raise ValidationError(
            "Source and destination hierarchies must be active."
        )

    if container.pk in destination_ancestors:
        raise ValidationError(
            "A container cannot move inside its own descendant."
        )

    if StorageLocation.objects.filter(
        parent=destination,
        name__iexact=container.name,
    ).exclude(pk=container.pk).exists():
        raise ValidationError(
            "The destination already contains a location "
            "with the same name."
        )

    affected_ids = _descendant_ids(container)

    assignments = SampleStorageAssignment.objects.filter(
        location_id__in=affected_ids,
        status="active",
    )

    return {
        "container_id": container.pk,
        "expected_parent_id": container.parent_id,
        "destination_id": destination.pk,
        "old_path": container.full_path,
        "new_path": (
            f"{destination.full_path} > {container.name}"
        ),
        "affected_location_count": len(affected_ids),
        "active_assignment_count": assignments.count(),
        "active_sample_count": (
            assignments.values("sample_id").distinct().count()
        ),
    }
