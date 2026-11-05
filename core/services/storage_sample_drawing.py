"""Drawings of where a Sample sits, for the Sample detail and edit pages."""

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocationLayoutV8146C3,
)
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
    can_view_storage_location,
)


def build_sample_storage_drawings(sample, user):
    """One entry per active assignment (path, layout, neighbours)."""
    assignments = list(
        sample.storage_assignments.filter(status="active")
        .select_related("location")
        .order_by("rank", "pk")
    )
    can_move = can_operate_on_sample_storage(user, sample)
    result = []

    for assignment in assignments:
        location = assignment.location

        if not can_view_storage_location(user, location):
            continue

        layout = StorageLocationLayoutV8146C3.objects.filter(
            location=location
        ).first()
        drawn = layout is not None and layout.organization in (
            "grid", "slots"
        )
        neighbours = []

        if drawn:
            neighbours = list(
                SampleStorageAssignment.objects.filter(
                    location=location, status="active"
                )
                .exclude(pk=assignment.pk)
                .exclude(position="")
                .values_list("position", flat=True)
            )

        result.append({
            "assignment_id": assignment.pk,
            "location_id": location.pk,
            "name": location.name,
            "path": location.full_path,
            "position": assignment.position,
            "primary": assignment.is_primary,
            "organization": layout.organization if drawn else "free",
            "rows": layout.rows if drawn else 0,
            "columns": layout.columns if drawn else 0,
            "slots": list(layout.slot_labels or []) if drawn else [],
            "direction": layout.slot_direction if drawn else "column",
            "others": neighbours,
            "can_move": can_move,
        })

    return result
