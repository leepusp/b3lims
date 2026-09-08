"""Physical Sample storage hierarchy and compatibility helpers."""

from django.db import transaction


def _safe_text(value):
    if value is None:
        return ""

    return str(value).strip()


def split_location_text(storage_location_text):
    """
    Parse one or more physical storage paths.

    Convention:
    - semicolon separates independent locations;
    - ">" or comma separates hierarchy levels.

    Example:
        Freezer A > Rack 1 > Box 2;
        Freezer B > Rack 4 > Box 9
    """

    text = _safe_text(
        storage_location_text
    )

    if not text:
        return []

    paths = []

    for raw_path in text.split(";"):
        raw_path = raw_path.strip()

        if not raw_path:
            continue

        levels = [
            level.strip()
            for level in (
                raw_path
                .replace(">", ",")
                .split(",")
            )
            if level.strip()
        ]

        if levels:
            paths.append(
                levels
            )

    return paths


def _canonical_path(levels):
    return " > ".join(
        _safe_text(level)
        for level in levels
        if _safe_text(level)
    )


def _get_or_create_location_path(
    levels,
):
    """
    Materialize one hierarchical StorageLocation path.

    Text-imported locations use location_type="other".
    Physical type classification is deliberately not inferred from
    human-readable names.
    """

    from core.models.samples.storage import (
        StorageLocation,
    )

    parent = None
    node = None

    for rank, raw_name in enumerate(
        levels,
        start=1,
    ):
        name = _safe_text(
            raw_name
        )

        if not name:
            continue

        node = (
            StorageLocation.objects
            .filter(
                parent=parent,
                name=name,
            )
            .order_by(
                "pk"
            )
            .first()
        )

        if node is None:
            node = StorageLocation.objects.create(
                parent=parent,
                name=name,
                location_type="other",
                rank=rank,
            )

        parent = node

    return node


def _sync_legacy_storage_levels(
    sample,
    primary_levels,
):
    """
    Keep SampleStorageLevel synchronized as a compatibility layer.

    The legacy representation supports one hierarchical location,
    therefore only the primary canonical path is represented here.
    """

    from core.models.samples.sample import (
        SampleStorageLevel,
    )

    (
        SampleStorageLevel.objects
        .filter(
            sample=sample
        )
        .delete()
    )

    for level_index, level_name in enumerate(
        primary_levels
    ):
        SampleStorageLevel.objects.create(
            sample=sample,
            name=level_name,
            level_index=level_index,
        )


@transaction.atomic
def assign_sample_storage_from_text(
    sample,
    storage_location_text,
    replace_existing=True,
    sync_legacy_field=True,
):
    """
    Materialize Sample physical storage from human-readable text.

    Canonical representation:
        StorageLocation
        SampleStorageAssignment

    Compatibility representation:
        Sample.storage_location
        SampleStorageLevel

    Multiple paths may be separated by semicolons. The first path is
    the primary location and is mirrored into the compatibility fields.

    Existing StorageLocation nodes are reused. Replacing a Sample's
    assignments does not delete shared StorageLocation records.
    """

    from core.models.samples.storage import (
        SampleStorageAssignment,
    )

    paths = split_location_text(
        storage_location_text
    )

    primary_levels = (
        paths[0]
        if paths
        else []
    )

    primary_path = _canonical_path(
        primary_levels
    )

    if replace_existing:
        (
            SampleStorageAssignment.objects
            .filter(
                sample=sample
            )
            .delete()
        )

        first_rank = 1

    else:
        latest = (
            SampleStorageAssignment.objects
            .filter(
                sample=sample
            )
            .order_by(
                "-rank"
            )
            .first()
        )

        first_rank = (
            latest.rank + 1
            if latest is not None
            else 1
        )

    for offset, levels in enumerate(
        paths
    ):
        location = (
            _get_or_create_location_path(
                levels
            )
        )

        if location is None:
            continue

        rank = (
            first_rank + offset
        )

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=location,
            rank=rank,
            is_primary=(
                rank == 1
            ),
            status="active",
        )

    if replace_existing:
        _sync_legacy_storage_levels(
            sample,
            primary_levels,
        )

    elif primary_levels:
        # SampleStorageLevel cannot faithfully represent multiple
        # independent paths. Do not overwrite an existing legacy
        # primary path when appending secondary assignments.
        if not sample.storage_levels.exists():
            _sync_legacy_storage_levels(
                sample,
                primary_levels,
            )

    if (
        sync_legacy_field
        and hasattr(
            sample,
            "storage_location",
        )
    ):
        if replace_existing:
            sample.storage_location = (
                primary_path
            )

        elif (
            primary_path
            and not _safe_text(
                sample.storage_location
            )
        ):
            sample.storage_location = (
                primary_path
            )

        sample.save(
            update_fields=[
                "storage_location",
            ]
        )

    return primary_levels


def get_all_storage_paths(
    sample,
):
    """
    Return all known storage paths for a Sample.

    Priority:
    1. canonical SampleStorageAssignment rows;
    2. legacy SampleStorageLevel rows;
    3. legacy Sample.storage_location text.
    """

    try:
        assignments = (
            sample
            .storage_assignments
            .select_related(
                "location"
            )
            .filter(
                status="active"
            )
            .order_by(
                "rank",
                "id",
            )
        )

        paths = [
            assignment.location.full_path
            for assignment
            in assignments
        ]

        if paths:
            return paths

    except Exception:
        pass

    try:
        levels = (
            sample
            .storage_levels
            .order_by(
                "level_index",
                "id",
            )
        )

        names = [
            _safe_text(
                level.name
            )
            for level in levels
            if _safe_text(
                level.name
            )
        ]

        if names:
            return [
                _canonical_path(
                    names
                )
            ]

    except Exception:
        pass

    legacy = _safe_text(
        getattr(
            sample,
            "storage_location",
            "",
        )
    )

    return (
        [legacy]
        if legacy
        else []
    )


def get_primary_storage_path(
    sample,
):
    paths = get_all_storage_paths(
        sample
    )

    return (
        paths[0]
        if paths
        else ""
    )


def build_storage_path_text(
    assignments,
):
    paths = []

    for assignment in assignments:
        try:
            paths.append(
                assignment.location.full_path
            )
        except Exception:
            pass

    return "; ".join(
        paths
    )
