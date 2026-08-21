from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models.events.model import Event
from core.models.samples.sample import SampleDeletionAudit
from core.services.sample_data_storage import sample_data_storage
from core.services.storage_locations import get_all_storage_paths


TRASH_RETENTION_DAYS = 30


def _json_value(value):
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        (
            datetime,
            date,
            time,
        ),
    ):
        return value.isoformat()

    if isinstance(
        value,
        (
            UUID,
            Decimal,
        ),
    ):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_value(item)
            for item in value
        ]

    return str(value)


def _model_snapshot(instance):
    data = {}

    for field in instance._meta.concrete_fields:
        try:
            value = field.value_from_object(
                instance
            )
        except Exception:
            value = getattr(
                instance,
                field.attname,
                None,
            )

        data[field.name] = _json_value(
            value
        )

    return data


def _manager_snapshots(manager):
    try:
        return [
            _model_snapshot(obj)
            for obj in manager.all()
        ]
    except Exception:
        return []


def _sample_subtype_snapshot(sample):
    for accessor in (
        "bacteria",
        "phage",
        "plasmid",
    ):
        try:
            obj = getattr(
                sample,
                accessor,
            )
        except Exception:
            continue

        if obj is not None:
            return {
                "model": obj._meta.label,
                "data": _model_snapshot(
                    obj
                ),
            }

    return None


def build_sample_deletion_snapshot(sample):
    """
    Build a JSON-serializable record before Sample.delete() cascades.

    The snapshot includes the audit/event trail and references that would
    otherwise disappear or become NULL after permanent deletion.
    """
    files = []

    for sample_file in sample.files.all():
        files.append(
            {
                "id": sample_file.pk,
                "logical_name": (
                    str(
                        sample_file.file.name
                    )
                    if sample_file.file
                    else ""
                ),
                "filename": sample_file.filename,
                "category": sample_file.category,
                "description": sample_file.description,
                "mime_type": sample_file.mime_type,
                "file_size": sample_file.file_size,
                "uploaded_at": _json_value(
                    sample_file.uploaded_at
                ),
            }
        )

    notebook_mentions = []

    try:
        for entry in sample.notebook_mentions.all():
            notebook_mentions.append(
                {
                    "id": entry.pk,
                    "title": getattr(
                        entry,
                        "title",
                        "",
                    ),
                    "author_id": getattr(
                        entry,
                        "author_id",
                        None,
                    ),
                    "created_at": _json_value(
                        getattr(
                            entry,
                            "created_at",
                            None,
                        )
                    ),
                }
            )
    except Exception:
        pass

    return {
        "sample": _model_snapshot(
            sample
        ),
        "subtype": _sample_subtype_snapshot(
            sample
        ),
        "collections": _manager_snapshots(
            sample.collections
        ),
        "tags": _manager_snapshots(
            sample.tags
        ),
        "keywords": _manager_snapshots(
            sample.keywords
        ),
        "origin": (
            _model_snapshot(
                sample.origin
            )
            if hasattr(
                sample,
                "origin",
            )
            else None
        ),
        "physical_storage_paths": [
            str(path)
            for path in get_all_storage_paths(
                sample
            )
        ],
        "storage_assignments": _manager_snapshots(
            sample.storage_assignments
        ),
        "storage_levels": _manager_snapshots(
            sample.storage_levels
        ),
        "files": files,
        "events": _manager_snapshots(
            sample.events
        ),
        "outgoing_relationships": _manager_snapshots(
            sample.outgoing_relationships
        ),
        "incoming_relationships": _manager_snapshots(
            sample.incoming_relationships
        ),
        "intake_records": _manager_snapshots(
            sample.intake_records
        ),
        "shipment_items": _manager_snapshots(
            sample.shipment_items
        ),
        "notebook_mentions": notebook_mentions,
        "notebook_sample_links": _manager_snapshots(
            sample.notebook_sample_links
        ),
        "molecular_sequences": _manager_snapshots(
            sample.molecular_sequences
        ),
    }


def _record_lifecycle_event(
    sample,
    user,
    note,
):
    Event.objects.create(
        sample=sample,
        performed_by=user,
        event_type="update",
        location_snapshot=(
            sample.storage_location
            or ""
        ),
        notes=note,
    )


@transaction.atomic
def deactivate_sample(
    sample,
    user,
):
    if sample.deletion_requested_at is not None:
        raise ValidationError(
            "A Sample in Trash cannot be deactivated. Restore it first."
        )

    if not sample.is_active:
        return sample

    now = timezone.now()

    sample.is_active = False
    sample.deactivated_at = now
    sample.deactivated_by = user

    sample.save(
        update_fields=[
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "updated_at",
        ]
    )

    _record_lifecycle_event(
        sample,
        user,
        "Sample deactivated.",
    )

    return sample


@transaction.atomic
def activate_sample(
    sample,
    user,
):
    if sample.deletion_requested_at is not None:
        raise ValidationError(
            "A Sample in Trash must be restored before it can be activated."
        )

    if sample.is_active:
        return sample

    sample.is_active = True
    sample.deactivated_at = None
    sample.deactivated_by = None

    sample.save(
        update_fields=[
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "updated_at",
        ]
    )

    _record_lifecycle_event(
        sample,
        user,
        "Sample reactivated.",
    )

    return sample


@transaction.atomic
def move_sample_to_trash(
    sample,
    user,
    retention_days=TRASH_RETENTION_DAYS,
):
    if sample.deletion_requested_at is not None:
        return sample

    if retention_days < 1:
        raise ValidationError(
            "Trash retention must be at least one day."
        )

    now = timezone.now()

    sample.is_active = False

    if sample.deactivated_at is None:
        sample.deactivated_at = now
        sample.deactivated_by = user

    sample.deletion_requested_at = now
    sample.deletion_requested_by = user
    sample.purge_after = (
        now
        + timedelta(
            days=retention_days
        )
    )

    sample.save(
        update_fields=[
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deletion_requested_at",
            "deletion_requested_by",
            "purge_after",
            "updated_at",
        ]
    )

    _record_lifecycle_event(
        sample,
        user,
        (
            "Sample moved to Trash. "
            f"Retention period: {retention_days} days."
        ),
    )

    return sample


@transaction.atomic
def restore_sample(
    sample,
    user,
):
    if sample.deletion_requested_at is None:
        raise ValidationError(
            "This Sample is not in Trash."
        )

    sample.is_active = True
    sample.deactivated_at = None
    sample.deactivated_by = None
    sample.deletion_requested_at = None
    sample.deletion_requested_by = None
    sample.purge_after = None

    sample.save(
        update_fields=[
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deletion_requested_at",
            "deletion_requested_by",
            "purge_after",
            "updated_at",
        ]
    )

    _record_lifecycle_event(
        sample,
        user,
        "Sample restored from Trash.",
    )

    return sample


def purge_sample(
    sample,
    user,
    *,
    now=None,
):
    """
    Permanently remove a Sample only after its retention deadline.

    A standalone SampleDeletionAudit is committed in the same database
    transaction before Sample.delete() executes its CASCADE behavior.
    Physical SampleFile objects are removed only after the database
    transaction succeeds.
    """
    now = now or timezone.now()

    if sample.deletion_requested_at is None:
        raise ValidationError(
            "Only Samples in Trash may be permanently deleted."
        )

    if sample.purge_after is None:
        raise ValidationError(
            "This Sample has no purge eligibility timestamp."
        )

    if sample.purge_after > now:
        raise ValidationError(
            (
                "This Sample is still inside its retention period. "
                f"Permanent deletion becomes available at "
                f"{sample.purge_after.isoformat()}."
            )
        )

    snapshot = build_sample_deletion_snapshot(
        sample
    )

    file_names = [
        item["logical_name"]
        for item in snapshot.get(
            "files",
            [],
        )
        if item.get(
            "logical_name"
        )
    ]

    with transaction.atomic():
        audit = SampleDeletionAudit.objects.create(
            original_sample_pk=sample.pk,
            original_sample_uuid=sample.uuid,
            original_sample_id=sample.sample_id,
            original_sample_type=(
                sample.sample_type
                or ""
            ),
            original_organism_name=(
                sample.organism_name
                or ""
            ),
            deleted_by=user,
            snapshot=snapshot,
        )

        sample.delete()

    cleanup_errors = []

    for logical_name in file_names:
        try:
            sample_data_storage.delete(
                logical_name
            )
        except Exception as exc:
            cleanup_errors.append(
                {
                    "logical_name": logical_name,
                    "error": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                }
            )

    if cleanup_errors:
        audit.storage_cleanup_errors = (
            cleanup_errors
        )
        audit.save(
            update_fields=[
                "storage_cleanup_errors",
            ]
        )

    return audit, cleanup_errors
