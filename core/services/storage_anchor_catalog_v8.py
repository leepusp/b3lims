"""Read-only catalog of registered physical storage anchors."""

from django.core.exceptions import ValidationError

from core.permissions.storage_workspaces_v8 import (
    visible_storage_locations_for_user,
)


def build_storage_anchor_catalog(*, user):
    """
    Return registered physical locations with active ancestors.

    Never creates locations or infers occupancy or free capacity.
    Position-type legacy nodes are not selectable physical anchors.
    """
    rows = list(
        visible_storage_locations_for_user(user).values(
            "pk",
            "parent_id",
            "name",
            "location_type",
            "is_active",
            "rank",
        )
    )

    indexed = {row["pk"]: row for row in rows}
    cache = {}
    visiting = set()

    def resolve(pk):
        if pk in cache:
            return cache[pk]

        if pk in visiting:
            raise ValidationError(
                "Cyclic storage hierarchy detected."
            )

        row = indexed.get(pk)

        if (
            row is None
            or not row["is_active"]
            or row["location_type"] == "position"
        ):
            cache[pk] = None
            return None

        visiting.add(pk)

        try:
            parent_id = row["parent_id"]

            if parent_id is None:
                parts = (row["name"],)
            else:
                parent_parts = resolve(parent_id)

                if parent_parts is None:
                    cache[pk] = None
                    return None

                parts = (*parent_parts, row["name"])

            cache[pk] = parts
            return parts
        finally:
            visiting.remove(pk)

    from core.models.samples.storage import (
        SampleStorageAssignment,
        StorageLocationLayoutV8146C3,
    )

    layouts = {
        layout.location_id: layout
        for layout in StorageLocationLayoutV8146C3.objects.filter(
            location_id__in=list(indexed)
        ).exclude(organization="free")
    }
    occupied = {}

    for location_id, position in (
        SampleStorageAssignment.objects.filter(
            location_id__in=list(layouts), status="active"
        )
        .exclude(position="")
        .values_list("location_id", "position")
    ):
        occupied.setdefault(location_id, []).append(position)

    result = []

    for row in rows:
        parts = resolve(row["pk"])

        if parts is None:
            continue

        layout = layouts.get(row["pk"])

        result.append({
            "organization": layout.organization if layout else "free",
            "rows": layout.rows if layout else 0,
            "columns": layout.columns if layout else 0,
            "slots": list(layout.slot_labels or []) if layout else [],
            "direction": layout.slot_direction if layout else "column",
            "occupied": occupied.get(row["pk"], []),
            "id": row["pk"],
            "parent_id": row["parent_id"],
            "name": row["name"],
            "location_type": row["location_type"],
            "full_path": " > ".join(parts),
            "depth": len(parts) - 1,
            "rank": row["rank"],
        })

    result.sort(
        key=lambda item: (
            item["full_path"].casefold(),
            item["id"],
        )
    )

    return result
