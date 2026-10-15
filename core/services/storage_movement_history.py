"""Conservative, workspace-scoped physical Storage history."""

from core.models.samples.storage import (
    StorageLocation,
    StorageMovement,
)
from core.permissions.storage_workspaces_v8 import (
    can_manage_storage_workspace,
    can_operate_on_sample_storage,
    can_view_storage_location,
    is_storage_global_admin,
)


# Bound the work performed by one HTTP request.
# A future paginated history endpoint can use cursor-based
# traversal over all events.
MAX_HISTORY_CANDIDATES = 1000


def _location_accessible(user, location_id, cache):
    """Resolve and authorize a physical location, with caching."""
    if location_id is None:
        return False

    if location_id not in cache:
        location = (
            StorageLocation.objects
            .select_related("workspace", "parent")
            .filter(pk=location_id)
            .first()
        )

        cache[location_id] = (
            location,
            bool(
                location is not None
                and can_view_storage_location(user, location)
            ),
        )

    return cache[location_id][1]


def _movement_visible_to_user(user, event, cache):
    """Deny the complete event if any participant is inaccessible."""
    allowed_types = {
        "registration",
        "sample",
        "sample_bulk",
        "container",
    }

    if event.movement_type not in allowed_types:
        return False

    # Every surviving location FK in the event header
    # must also be currently accessible.
    for field in (
        "moved_location_id",
        "origin_location_id",
        "destination_location_id",
    ):
        pk = getattr(event, field)

        if pk is not None and not _location_accessible(
            user, pk, cache
        ):
            return False

    if event.movement_type == "container":
        # A container event without a surviving container
        # or physical destination cannot be scoped safely.
        if (
            event.moved_location_id is None
            or event.destination_location_id is None
        ):
            return False

        moved = event.moved_location
        destination = event.destination_location

        if (
            moved.workspace_id is None
            or moved.workspace_id != destination.workspace_id
            or not can_manage_storage_workspace(
                user, moved.workspace
            )
        ):
            return False

    items = list(event.items.all())

    if not items:
        # Only fully identified empty-container events
        # may be displayed outside global administration.
        return (
            event.movement_type == "container"
            and event.affected_sample_count == 0
            and event.affected_assignment_count == 0
        )

    # A mismatched audit count indicates incomplete evidence.
    if event.affected_assignment_count != len(items):
        return False

    if event.affected_sample_count != len({
        item.sample_id
        for item in items
        if item.sample_id is not None
    }):
        return False

    for item in items:
        if (
            item.sample_id is None
            or item.sample is None
            or item.location_id_snapshot is None
            or item.destination_location_id_snapshot is None
        ):
            return False

        if not can_operate_on_sample_storage(
            user, item.sample
        ):
            return False

        if not _location_accessible(
            user, item.location_id_snapshot, cache
        ):
            return False

        if not _location_accessible(
            user,
            item.destination_location_id_snapshot,
            cache,
        ):
            return False

    return True


def visible_storage_movements(user, *, limit=20):
    """Return only fully authorized movement events."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError(
            "History limit must be between 1 and 50."
        )

    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return StorageMovement.objects.none()

    ordered = StorageMovement.objects.order_by(
        "-created_at", "-pk"
    )

    if is_storage_global_admin(user):
        return ordered[:limit]

    candidates = (
        ordered
        .select_related(
            "moved_location__workspace",
            "origin_location",
            "destination_location",
        )
        .prefetch_related("items__sample")
    )[:MAX_HISTORY_CANDIDATES]

    allowed_ids = []
    location_cache = {}

    for event in candidates:
        if _movement_visible_to_user(
            user, event, location_cache
        ):
            allowed_ids.append(event.pk)

        if len(allowed_ids) >= limit:
            break

    return (
        StorageMovement.objects
        .filter(pk__in=allowed_ids)
        .order_by("-created_at", "-pk")[:limit]
    )
