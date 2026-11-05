"""Change the drawing (grid or named compartments) of an existing location.

A change is accepted only when every Sample recorded in the location still
has a valid position afterwards. Renaming a compartment carries its Samples
along; removing a compartment or shrinking a grid under Samples is refused.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocationLayoutV8146C3,
    clean_slot_labels,
)
from core.services.storage_layout_position import position_for_layout
from core.services.storage_workspace_infrastructure_v8 import (
    _managed_location,
)
from core.services.storage_writer_lock import acquire_storage_writer_lock


def _dimension(value, maximum, label):
    token = str(value or "").strip()
    if not (
        token.isascii() and token.isdecimal() and 1 <= len(token) <= 3
        and 1 <= int(token) <= maximum
    ):
        raise ValidationError(f"{label} must be between 1 and {maximum}.")
    return int(token)


@transaction.atomic
def update_location_layout(
    *, actor, location_id, organization, rows=None, columns=None,
    slot_labels=(), slot_old=(), direction="column",
):
    acquire_storage_writer_lock()
    location = _managed_location(actor, location_id)

    if organization not in {"free", "grid", "slots"}:
        raise ValidationError("Select a valid storage organization.")

    layout = StorageLocationLayoutV8146C3.objects.filter(
        location=location
    ).first()
    if layout is None:
        layout = StorageLocationLayoutV8146C3(
            location=location, organization="free"
        )

    old_rows = []
    if organization == "slots":
        labels = clean_slot_labels(list(slot_labels))
        olds = list(slot_old) + [""] * (len(labels) - len(slot_old))
        if direction not in {"column", "row"}:
            raise ValidationError("Select a valid compartment direction.")
    else:
        labels, olds = [], []

    assignments = list(
        SampleStorageAssignment.objects.select_for_update()
        .filter(location=location, status="active")
        .exclude(position="")
    )

    renames = {}
    if organization == "slots" and layout.organization == "slots":
        kept = {name.lower() for name in (layout.slot_labels or [])}
        for new, old in zip(labels, olds):
            old = " ".join(str(old).split())
            if old and old.lower() in kept and old.lower() != new.lower():
                renames[old.lower()] = new
        # A name taken from another compartment would collide mid-way.
        clash = {old for old in renames} & {
            new.lower() for new in renames.values()
        }
        if clash:
            raise ValidationError(
                "Rename in two steps: a new name equals the old name of "
                "another compartment."
            )
        for item in assignments:
            key = " ".join(item.position.split()).lower()
            if key in renames:
                item.position = renames[key]
                item.save(update_fields=["position"])

    layout.organization = organization
    layout.rows = _dimension(rows, 26, "Rows") if organization == "grid" else 0
    layout.columns = (
        _dimension(columns, 24, "Columns") if organization == "grid" else 0
    )
    layout.slot_labels = labels
    layout.slot_direction = direction if organization == "slots" else "column"
    layout.full_clean()
    layout.save()

    stranded = []
    for item in assignments:
        try:
            position_for_layout(location, item.position)
        except ValidationError:
            stranded.append(item.position)

    if stranded:
        shown = ", ".join(sorted(set(stranded))[:6])
        raise ValidationError(
            f"{len(stranded)} Sample(s) sit in positions that would no "
            f"longer exist ({shown}). Move them first, then change the "
            "drawing."
        )

    return location, layout, len(renames)
