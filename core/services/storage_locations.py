def _safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def split_location_text(storage_location_text):
    """
    Parse storage paths.

    Convention:
    - semicolon separates multiple independent locations
    - ">" or comma separates hierarchy levels in the same location
    """
    text = _safe_text(storage_location_text)
    if not text:
        return []

    paths = []

    for raw_path in text.split(";"):
        raw_path = raw_path.strip()
        if not raw_path:
            continue

        levels = [
            level.strip()
            for level in raw_path.replace(">", ",").split(",")
            if level.strip()
        ]

        if levels:
            paths.append(levels)

    return paths


def _canonical_path(levels):
    return " > ".join([_safe_text(level) for level in levels if _safe_text(level)])


def assign_sample_storage_from_text(
    sample,
    storage_location_text,
    replace_existing=True,
    sync_legacy_field=True,
):
    """
    Compatibility layer for the current clone.

    Uses the existing Sample.storage_location field and, when available,
    the legacy SampleStorageLevel table.
    """
    paths = split_location_text(storage_location_text)
    primary_levels = paths[0] if paths else []
    primary_path = _canonical_path(primary_levels)

    if replace_existing:
        try:
            from core.models.samples.sample import SampleStorageLevel
            SampleStorageLevel.objects.filter(sample=sample).delete()
        except Exception:
            pass

    if primary_levels:
        try:
            from core.models.samples.sample import SampleStorageLevel

            for level_index, level_name in enumerate(primary_levels):
                SampleStorageLevel.objects.create(
                    sample=sample,
                    name=level_name,
                    level_index=level_index,
                )
        except Exception:
            pass

    if sync_legacy_field and hasattr(sample, "storage_location"):
        sample.storage_location = primary_path
        sample.save(update_fields=["storage_location"])

    return primary_levels


def get_all_storage_paths(sample):
    """
    Return all known storage paths for a sample.

    Priority:
    1. New storage_assignments relation, if present
    2. Legacy SampleStorageLevel rows, if present
    3. Sample.storage_location text
    """
    try:
        assignments = (
            sample.storage_assignments
            .select_related("location")
            .filter(status="active")
            .order_by("rank", "id")
        )

        paths = [assignment.location.full_path for assignment in assignments]

        if paths:
            return paths
    except Exception:
        pass

    try:
        levels = sample.storage_levels.order_by("level_index", "id")
        names = [_safe_text(level.name) for level in levels if _safe_text(level.name)]
        if names:
            return [_canonical_path(names)]
    except Exception:
        pass

    legacy = _safe_text(getattr(sample, "storage_location", ""))
    return [legacy] if legacy else []


def get_primary_storage_path(sample):
    paths = get_all_storage_paths(sample)
    return paths[0] if paths else ""


def build_storage_path_text(assignments):
    paths = []

    for assignment in assignments:
        try:
            paths.append(assignment.location.full_path)
        except Exception:
            pass

    return "; ".join(paths)
