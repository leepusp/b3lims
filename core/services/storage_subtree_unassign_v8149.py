"""Preview and atomically release Samples from deleted storage subtrees."""

import hashlib
import json
from collections import defaultdict

from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
)
from core.services.storage_legacy_sync import (
    sync_primary_storage_legacy_for_samples,
)
from core.services.storage_locations import (
    _sync_legacy_storage_levels,
    split_location_text,
)
from core.services.storage_subtree_delete_v8145 import _analyze
from core.services.storage_writer_lock import acquire_storage_writer_lock


SALT = "b3lims-storage-subtree-unassign-v8149"
ALLOWED_DEPENDENCIES = frozenset({
    "core.StorageMovement",
    "core.StorageSceneConfiguration",
    "core.StorageLocationLayoutV8146C3",
    "StorageMovementItem snapshots",
    "StorageMovement path snapshots",
    "StorageMovementItem path snapshots",
})


def _normalize_path(path):
    return " > ".join(
        part.strip()
        for part in str(path or "").split(">")
        if part.strip()
    ).casefold()


def _legacy_paths(sample):
    return [
        " > ".join(parts)
        for parts in split_location_text(
            sample.storage_location or ""
        )
    ]


def _under_deleted(path, deleted_paths):
    candidate = _normalize_path(path)
    return any(
        candidate == prefix
        or candidate.startswith(prefix + " > ")
        for prefix in deleted_paths
    )


def _inspect(actor, location_id, *, lock=False):
    base = _analyze(actor, location_id, lock=lock)
    ids = base["ids"]
    id_set = set(ids)

    locations = list(
        StorageLocation.objects
        .filter(pk__in=ids)
        .order_by("pk")
    )

    location_paths = {
        loc.pk: loc.full_path
        for loc in locations
    }
    prefixes = {
        _normalize_path(path)
        for path in location_paths.values()
    }

    all_assignments = list(
        SampleStorageAssignment.objects
        .filter(location_id__in=ids)
        .order_by("sample_id", "rank", "pk")
    )
    sample_ids = {
        assignment.sample_id
        for assignment in all_assignments
    }

    textual_query = Q(pk__in=sample_ids)

    for path in location_paths.values():
        if path:
            textual_query |= Q(
                storage_location__icontains=path
            )

    candidates = list(
        Sample.objects
        .filter(textual_query)
        .order_by("pk")
    )

    samples = [
        sample for sample in candidates
        if sample.pk in sample_ids
        or any(
            _under_deleted(path, prefixes)
            for path in _legacy_paths(sample)
        )
    ]

    affected_ids = {sample.pk for sample in samples}

    remaining_assignments = list(
        SampleStorageAssignment.objects
        .filter(sample_id__in=affected_ids)
        .order_by("sample_id", "rank", "pk")
    )

    if lock and affected_ids:
        list(
            Sample.objects.select_for_update()
            .filter(pk__in=affected_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        list(
            SampleStorageAssignment.objects.select_for_update()
            .filter(sample_id__in=affected_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )

    remaining_by_sample = defaultdict(list)
    for assignment in remaining_assignments:
        remaining_by_sample[assignment.sample_id].append(
            assignment
        )

    legacy_conflict_count = 0

    for sample in samples:
        surviving_active = [
            assignment
            for assignment in remaining_by_sample[sample.pk]
            if (
                assignment.status == "active"
                and assignment.location_id not in id_set
            )
        ]

        if not surviving_active:
            continue

        valid_paths = {
            _normalize_path(
                assignment.location.full_path + (
                    " > " + assignment.position
                    if (
                        assignment.position
                        and assignment.location.location_type
                        != "position"
                    )
                    else ""
                )
            )
            for assignment in surviving_active
        }

        remaining_legacy = [
            path
            for path in _legacy_paths(sample)
            if not _under_deleted(path, prefixes)
        ]

        if any(
            _normalize_path(path) not in valid_paths
            for path in remaining_legacy
        ):
            legacy_conflict_count += 1

    orphaned_count = 0
    for sample in samples:
        active_outside = any(
            assignment.status == "active"
            and assignment.location_id not in id_set
            for assignment in remaining_by_sample[sample.pk]
        )
        retained_legacy = any(
            not _under_deleted(path, prefixes)
            for path in _legacy_paths(sample)
        )
        if not active_outside and not retained_legacy:
            orphaned_count += 1

    blocked_dependencies = {
        key: value
        for key, value in base["blockers"].items()
        if key not in ALLOWED_DEPENDENCIES
    }

    unauthorized_count = sum(
        not can_operate_on_sample_storage(actor, sample)
        for sample in samples
    )

    fingerprint_data = {
        "root": base["root_id"],
        "locations": [
            (
                loc.pk, loc.parent_id, loc.workspace_id,
                loc.name, loc.location_type, loc.is_active,
            )
            for loc in locations
        ],
        "assignments": [
            (
                a.pk, a.sample_id, a.location_id, a.rank,
                a.is_primary, a.status, a.position,
                a.container_type, str(a.quantity),
                a.quantity_unit, a.notes,
            )
            for a in remaining_assignments
        ],
        "samples": [
            (s.pk, s.sample_id, s.storage_location)
            for s in samples
        ],
        "dependencies": base["blockers"],
    }

    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_data,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    preview = {
        "root_id": base["root_id"],
        "root_path": base["root_path"],
        "location_count": base["location_count"],
        "descendant_count": base["descendant_count"],
        "sample_count": len(samples),
        "assignment_count": len(all_assignments),
        "textual_count": sum(
            any(
                _under_deleted(path, prefixes)
                for path in _legacy_paths(sample)
            )
            for sample in samples
        ),
        "orphaned_count": orphaned_count,
        "retained_sample_count": len(samples) - orphaned_count,
        "blockers": base["blockers"],
        "blocked_dependencies": blocked_dependencies,
        "unauthorized_sample_count": unauthorized_count,
        "legacy_conflict_count": legacy_conflict_count,
        "can_delete": base["can_delete"],
        "can_unassign": (
            not blocked_dependencies
            and unauthorized_count == 0
            and legacy_conflict_count == 0
        ),
        "fingerprint": fingerprint,
    }

    return {
        "preview": preview,
        "ids": ids,
        "prefixes": prefixes,
        "paths": location_paths,
        "samples": samples,
        "assignments": remaining_by_sample,
    }


def preview_storage_subtree_unassign_v8149(*, actor, location_id):
    """Read-only impact preview with short-lived confirmation token."""
    state = _inspect(actor, location_id)
    result = dict(state["preview"])

    if result["can_unassign"]:
        result["confirm_token"] = signing.dumps(
            {
                "actor": actor.pk,
                "root": result["root_id"],
                "fingerprint": result["fingerprint"],
            },
            salt=SALT,
        )
    else:
        result["confirm_token"] = ""

    result.pop("fingerprint")
    return result


@transaction.atomic
def delete_storage_subtree_unassign_v8149(
    *,
    actor,
    location_id,
    confirmation,
    preview_token,
    reason,
):
    """Unassign affected Samples and remove an authorized subtree atomically."""
    if confirmation != "DELETE":
        raise ValidationError(
            "Explicit DELETE confirmation is required."
        )

    reason = str(reason or "").strip()
    if not 5 <= len(reason) <= 1000:
        raise ValidationError(
            "A deletion reason between 5 and 1000 characters is required."
        )

    try:
        signed = signing.loads(
            preview_token or "",
            salt=SALT,
            max_age=600,
        )
    except signing.BadSignature as exc:
        raise ValidationError(
            "Deletion preview expired or is invalid."
        ) from exc

    if (
        signed.get("actor") != actor.pk
        or str(signed.get("root")) != str(location_id)
    ):
        raise ValidationError(
            "Deletion confirmation does not match the selected location."
        )

    acquire_storage_writer_lock()
    state = _inspect(actor, location_id, lock=True)
    preview = state["preview"]

    if signed.get("fingerprint") != preview["fingerprint"]:
        raise ValidationError(
            "Storage assignments changed after preview. Review again."
        )

    if not preview["can_unassign"]:
        raise PermissionDenied(
            "The subtree has unauthorized or protected dependencies."
        )

    ids = set(state["ids"])
    prefixes = state["prefixes"]
    affected_ids = {sample.pk for sample in state["samples"]}
    audit_rows = []
    active_survivor_ids = set()

    for sample in state["samples"]:
        assignments = list(
            state["assignments"][sample.pk]
        )
        removed = [
            a for a in assignments
            if a.location_id in ids
        ]
        survivors = [
            a for a in assignments
            if a.location_id not in ids
        ]

        audit_rows.append({
            "sample_id": sample.pk,
            "sample_identifier": sample.sample_id,
            "legacy_before": sample.storage_location,
            "removed": [
                {
                    "assignment_id": a.pk,
                    "location_id": a.location_id,
                    "path": state["paths"][a.location_id],
                    "position": a.position,
                    "rank": a.rank,
                    "status": a.status,
                    "container_type": a.container_type,
                    "quantity": str(a.quantity),
                    "quantity_unit": a.quantity_unit,
                    "notes": a.notes,
                }
                for a in removed
            ],
        })

        # Free existing rank values before assigning new ranks.
        max_rank = max(
            (a.rank for a in assignments),
            default=0,
        )
        for index, a in enumerate(survivors, start=1):
            SampleStorageAssignment.objects.filter(
                pk=a.pk
            ).update(
                rank=max_rank + len(assignments) + index,
                is_primary=False,
            )

        if removed:
            SampleStorageAssignment.objects.filter(
                pk__in=[a.pk for a in removed]
            ).delete()

        survivors.sort(
            key=lambda a: (
                a.status != "active",
                a.rank,
                a.pk,
            )
        )
        first_active = next(
            (a.pk for a in survivors if a.status == "active"),
            None,
        )

        for rank, a in enumerate(survivors, start=1):
            SampleStorageAssignment.objects.filter(
                pk=a.pk
            ).update(
                rank=rank,
                is_primary=(a.pk == first_active),
            )

        remaining_text = [
            path for path in _legacy_paths(sample)
            if not _under_deleted(path, prefixes)
        ]

        active_survivors = [
            a for a in survivors if a.status == "active"
        ]

        if active_survivors:
            # Preserve authoritative structured storage. Do not silently
            # discard an unrelated legacy-only secondary location.
            structured_paths = {
                _normalize_path(
                    a.location.full_path + (
                        " > " + a.position
                        if a.position and
                        a.location.location_type != "position"
                        else ""
                    )
                )
                for a in active_survivors
            }
            if any(
                _normalize_path(path) not in structured_paths
                for path in remaining_text
            ):
                raise ValidationError(
                    "A Sample has an unmatched legacy storage path. "
                    "Reconcile it before deleting this subtree."
                )
            active_survivor_ids.add(sample.pk)
        else:
            new_text = "; ".join(remaining_text)
            Sample.objects.filter(pk=sample.pk).update(
                storage_location=new_text
            )
            _sync_legacy_storage_levels(
                sample,
                split_location_text(new_text)[0]
                if new_text else [],
            )

    if active_survivor_ids:
        sync_primary_storage_legacy_for_samples(
            sample_ids=active_survivor_ids
        )

    LogEntry.objects.create(
        user_id=actor.pk,
        content_type=ContentType.objects.get_for_model(
            StorageLocation
        ),
        object_id=str(preview["root_id"]),
        object_repr=preview["root_path"][:200],
        action_flag=DELETION,
        change_message=json.dumps({
            "operation": "delete_storage_subtree_unassign_v8149",
            "reason": reason,
            "location_ids": state["ids"],
            "location_paths": state["paths"],
            "sample_count": preview["sample_count"],
            "assignment_count": preview["assignment_count"],
            "samples": audit_rows,
        }),
    )

    count, by_model = StorageLocation.objects.filter(
        pk__in=state["ids"]
    ).delete()

    if by_model.get(StorageLocation._meta.label, 0) != \
            preview["location_count"]:
        raise ValidationError(
            "Storage deletion count mismatch; transaction reverted."
        )

    unexpected = {
        model: value
        for model, value in by_model.items()
        if model not in {
            StorageLocation._meta.label,
            "core.StorageSceneConfiguration",
            "core.StorageLocationLayoutV8146C3",
        }
        and value
    }

    if unexpected:
        raise ValidationError(
            "Unexpected dependent records; transaction reverted."
        )

    return {
        **{
            key: value
            for key, value in preview.items()
            if key != "fingerprint"
        },
        "deleted_database_rows": count,
        "dependent_deletions": by_model,
    }
