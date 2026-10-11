"""Synchronize legacy Sample storage from canonical assignments."""

from django.core.exceptions import ValidationError

from core.models.samples.sample import (
    Sample,
    SampleStorageLevel,
)
from core.models.samples.storage import SampleStorageAssignment
from core.services.storage_locations import (
    _sync_legacy_storage_levels,
)


def sync_primary_storage_legacy_for_samples(*, sample_ids):
    """
    Synchronize legacy representations of affected Samples.

    Must be called inside the movement transaction.

    Never creates, updates or deletes SampleStorageAssignment.
    """
    ids = sorted(set(sample_ids))

    if not ids:
        return 0

    # Follow the same ordering used by get_all_storage_paths().
    primary_assignments = {}

    assignments = (
        SampleStorageAssignment.objects
        .filter(
            sample_id__in=ids,
            status="active",
        )
        .select_related("location")
        .order_by("sample_id", "rank", "id")
    )

    for assignment in assignments:
        primary_assignments.setdefault(
            assignment.sample_id,
            assignment,
        )

    samples = list(
        Sample.objects
        .select_for_update()
        .filter(pk__in=primary_assignments)
        .order_by("pk")
    )

    # Validate everything before writing legacy records.
    updates = []

    for sample in samples:
        assignment = primary_assignments[sample.pk]
        path = assignment.location.full_path
        levels = list(assignment.location.full_path_parts)

        if len(path) > 255:
            raise ValidationError(
                f"Sample {sample.sample_id}: storage path "
                "exceeds the 255-character legacy limit."
            )

        if any(len(name) > 150 for name in levels):
            raise ValidationError(
                f"Sample {sample.sample_id}: a storage level "
                "exceeds the 150-character legacy limit."
            )

        updates.append((sample, path, levels))

    for sample, path, levels in updates:
        # Bypass Sample.pre_save transfer signals.
        # The actual operation is audited by StorageMovement.
        if sample.storage_location != path:
            (
                Sample.objects
                .filter(pk=sample.pk)
                .update(storage_location=path)
            )

        current_levels = list(
            SampleStorageLevel.objects
            .filter(sample_id=sample.pk)
            .order_by("level_index", "id")
            .values_list("name", flat=True)
        )

        if current_levels != levels:
            _sync_legacy_storage_levels(
                sample,
                levels,
            )

    return len(updates)
