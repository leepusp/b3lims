"""Read-only spatial projection of registered StorageLocation trees."""

from django.core.exceptions import ValidationError

from core.models.samples.storage import StorageLocation


SCENE_PROFILES = frozenset({
    "space",
    "cabinet",
    "shelves",
    "rack",
    "grid",
    "generic",
})

DEFAULT_SCENE_PROFILES = {
    "room": "space",
    "freezer": "cabinet",
    "refrigerator": "cabinet",
    "shelf": "shelves",
    "rack": "rack",
    "box": "grid",
    "position": "grid",
    "other": "generic",
}


def _validated_profiles(profile_overrides):
    if profile_overrides is None:
        return {}

    if not isinstance(profile_overrides, dict):
        raise ValidationError(
            "Scene profile overrides must be a mapping."
        )

    result = {}

    for raw_id, profile in profile_overrides.items():
        try:
            location_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Invalid scene profile location ID."
            ) from exc

        if location_id <= 0 or profile not in SCENE_PROFILES:
            raise ValidationError(
                "Invalid location ID or geometry profile."
            )

        result[location_id] = profile

    return result


def build_storage_scene_projection(
    *,
    root_id,
    profile_overrides=None,
    include_inactive=False,
    max_depth=16,
    max_nodes=1000,
):
    """
    Represent any registered physical node as a spatial scene root.

    Reads the physical hierarchy without changing its parent links,
    creating virtual StorageLocation records or assigning Samples.

    Does not include Sample information. Sample visibility and occupancy
    must be handled separately by an authorized application view.
    """
    if (
        not isinstance(max_depth, int)
        or isinstance(max_depth, bool)
        or max_depth < 0
        or not isinstance(max_nodes, int)
        or isinstance(max_nodes, bool)
        or max_nodes < 1
    ):
        raise ValidationError("Invalid scene size limits.")

    profiles = _validated_profiles(profile_overrides)

    try:
        root_pk = int(root_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid scene root.") from exc

    root = StorageLocation.objects.filter(pk=root_pk).first()

    if root is None:
        raise ValidationError("Scene root does not exist.")

    # Check the selected root and its ancestors.
    ancestors = set()
    ancestor = root

    while ancestor is not None:
        if ancestor.pk in ancestors:
            raise ValidationError("Cyclic storage hierarchy.")

        ancestors.add(ancestor.pk)

        if not include_inactive and not ancestor.is_active:
            raise ValidationError(
                "An inactive location cannot be used in an active scene."
            )

        ancestor = ancestor.parent

    root_path = root.full_path
    paths = {root.pk: root_path}
    depths = {root.pk: 0}
    visited = {root.pk}

    def make_node(row, depth, path):
        return {
            "id": row["pk"],
            "parent_id": row["parent_id"],
            "name": row["name"],
            "location_type": row["location_type"],
            "is_active": row["is_active"],
            "depth": depth,
            "path": path,
            "geometry_profile": profiles.get(
                row["pk"],
                DEFAULT_SCENE_PROFILES.get(
                    row["location_type"],
                    "generic",
                ),
            ),
            "capacity": None,
        }

    root_row = {
        "pk": root.pk,
        "parent_id": root.parent_id,
        "name": root.name,
        "location_type": root.location_type,
        "is_active": root.is_active,
    }

    nodes = [make_node(root_row, 0, root_path)]
    edges = []
    frontier = [root.pk]

    while frontier:
        children = list(
            StorageLocation.objects
            .filter(parent_id__in=frontier)
            .order_by("parent_id", "rank", "name", "pk")
            .values(
                "pk",
                "parent_id",
                "name",
                "location_type",
                "is_active",
            )
        )

        if not include_inactive:
            children = [
                row for row in children
                if row["is_active"]
            ]

        if not children:
            break

        if len(nodes) + len(children) > max_nodes:
            raise ValidationError(
                "Scene contains too many physical locations."
            )

        next_frontier = []

        for row in children:
            pk = row["pk"]
            parent_id = row["parent_id"]

            if pk in visited:
                raise ValidationError(
                    "Cyclic storage hierarchy."
                )

            depth = depths[parent_id] + 1

            if depth > max_depth:
                raise ValidationError(
                    "Scene exceeds maximum hierarchy depth."
                )

            path = paths[parent_id] + " > " + row["name"]

            visited.add(pk)
            depths[pk] = depth
            paths[pk] = path

            nodes.append(make_node(row, depth, path))

            edges.append({
                "parent_id": parent_id,
                "child_id": pk,
            })

            next_frontier.append(pk)

        frontier = next_frontier

    return {
        "scene_root_id": root.pk,
        "scene_root_path": root_path,
        "nodes": nodes,
        "edges": edges,
        "sample_data_included": False,
        "read_only": True,
    }
