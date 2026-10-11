"""Physical Sample storage hierarchy and compatibility helpers."""

from django.core.exceptions import ValidationError
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

    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()

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

    # Repeated initialization of identical active paths must not
    # destroy physical positions or assignment metadata.
    if replace_existing:
        existing_assignments = list(
            SampleStorageAssignment.objects
            .select_for_update()
            .select_related("location")
            .filter(sample=sample)
            .order_by("rank", "pk")
        )

        requested_paths = [
            _canonical_path(levels)
            for levels in paths
        ]

        if (
            existing_assignments
            and all(
                assignment.status == "active"
                for assignment in existing_assignments
            )
            and [
                assignment.location.full_path
                for assignment in existing_assignments
            ] == requested_paths
        ):
            existing_levels = list(
                sample.storage_levels
                .order_by("level_index", "pk")
                .values_list("name", flat=True)
            )

            if existing_levels != primary_levels:
                _sync_legacy_storage_levels(
                    sample,
                    primary_levels,
                )

            if (
                sync_legacy_field
                and sample.storage_location != primary_path
            ):
                sample.storage_location = primary_path
                sample.save(
                    update_fields=["storage_location"]
                )

            return primary_levels

    if replace_existing:
        # Legacy initialization must not destroy populated physical
        # assignments. Existing physical changes require an audited
        # movement or an explicit lifecycle operation.
        if any(
            assignment.status != "active"
            or bool((assignment.position or "").strip())
            or bool((assignment.container_type or "").strip())
            or assignment.quantity is not None
            or bool((assignment.quantity_unit or "").strip())
            or bool((assignment.notes or "").strip())
            for assignment in existing_assignments
        ):
            raise ValidationError(
                "Existing physical assignments cannot be replaced "
                "or cleared through legacy initialization. "
                "Use an audited movement."
            )

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



def _validated_location_name(value):
    name = _safe_text(
        value
    )

    if not name:
        raise ValidationError(
            "Storage location name is required."
        )

    if len(name) > 255:
        raise ValidationError(
            "Storage location name is too long."
        )

    return name


def _validated_location_type(value):
    from core.models.samples.storage import (
        StorageLocation,
    )

    raw = _safe_text(
        value
    ) or "other"

    valid = {
        choice[0]
        for choice
        in StorageLocation.LOCATION_TYPE_CHOICES
    }

    if raw not in valid:
        raise ValidationError(
            "Invalid storage location type."
        )

    return raw


def _validated_rank(value):
    try:
        rank = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValidationError(
            "Storage rank must be an integer."
        ) from exc

    if rank < 1:
        raise ValidationError(
            "Storage rank must be at least 1."
        )

    return rank


def _ensure_unique_location_name(
    *,
    name,
    parent,
    exclude_pk=None,
):
    from core.models.samples.storage import (
        StorageLocation,
    )

    query = (
        StorageLocation.objects
        .filter(
            parent=parent,
            name__iexact=name,
        )
    )

    if exclude_pk is not None:
        query = query.exclude(
            pk=exclude_pk
        )

    if query.exists():
        raise ValidationError(
            (
                "A storage location with this name "
                "already exists under the same parent."
            )
        )


@transaction.atomic
def create_storage_location(
    *,
    name,
    parent=None,
    location_type="other",
    rank=1,
    notes="",
):
    """
    Create one explicitly managed physical storage node.
    """

    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()

    from core.models.samples.storage import (
        StorageLocation,
    )

    name = _validated_location_name(
        name
    )

    location_type = (
        _validated_location_type(
            location_type
        )
    )

    rank = _validated_rank(
        rank
    )

    if (
        parent is not None
        and not parent.is_active
    ):
        raise ValidationError(
            (
                "A child location cannot be created "
                "under an inactive parent."
            )
        )

    _ensure_unique_location_name(
        name=name,
        parent=parent,
    )

    return StorageLocation.objects.create(
        name=name,
        parent=parent,
        location_type=location_type,
        rank=rank,
        notes=_safe_text(
            notes
        ),
        is_active=True,
    )


@transaction.atomic
def update_storage_location(
    location,
    *,
    name,
    location_type,
    rank,
    notes="",
):
    """
    Update metadata without silently reparenting the hierarchy.
    """

    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()

    name = _validated_location_name(
        name
    )

    location_type = (
        _validated_location_type(
            location_type
        )
    )

    rank = _validated_rank(
        rank
    )

    _ensure_unique_location_name(
        name=name,
        parent=location.parent,
        exclude_pk=location.pk,
    )

    location.name = name
    location.location_type = (
        location_type
    )
    location.rank = rank
    location.notes = _safe_text(
        notes
    )

    location.save(
        update_fields=[
            "name",
            "location_type",
            "rank",
            "notes",
            "updated_at",
        ]
    )

    return location


@transaction.atomic
def set_storage_location_active(
    location,
    *,
    is_active,
):
    """
    Activate/deactivate an infrastructure node safely.

    A location that still contains active Samples or active child
    locations cannot be deactivated.
    """

    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()

    desired = bool(
        is_active
    )

    if desired == location.is_active:
        return location

    if desired:
        if (
            location.parent is not None
            and not location.parent.is_active
        ):
            raise ValidationError(
                (
                    "The parent location must be active "
                    "before this location can be reactivated."
                )
            )

    else:
        if location.children.filter(
            is_active=True
        ).exists():
            raise ValidationError(
                (
                    "Deactivate active child locations "
                    "before deactivating this location."
                )
            )

        if location.sample_assignments.filter(
            status="active"
        ).exists():
            raise ValidationError(
                (
                    "This location still contains active "
                    "Sample assignments."
                )
            )

    location.is_active = desired

    location.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    return location


@transaction.atomic
def assign_sample_to_storage_location(
    *,
    sample,
    location,
):
    """
    Set one existing active location as the Sample's canonical
    physical location.

    V1 intentionally replaces the current active assignment set.
    The legacy Sample.storage_location and SampleStorageLevel
    representations remain synchronized by the compatibility service.
    """

    from core.services.storage_writer_lock import acquire_storage_writer_lock
    acquire_storage_writer_lock()

    if not location.is_active:
        raise ValidationError(
            (
                "Samples cannot be assigned "
                "to an inactive storage location."
            )
        )

    assign_sample_storage_from_text(
        sample=sample,
        storage_location_text=(
            location.full_path
        ),
        replace_existing=True,
        sync_legacy_field=True,
    )

    return (
        sample.storage_assignments
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
        .first()
    )
