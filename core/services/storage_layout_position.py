"""Check a Sample position against the drawing of its location."""

import re

from django.core.exceptions import ValidationError

_GRID = re.compile(r"^([A-Za-z])0*([1-9][0-9]*)$")


def layout_of(location):
    from core.models.samples.storage import StorageLocationLayoutV8146C3

    return StorageLocationLayoutV8146C3.objects.filter(
        location_id=location.pk
    ).first()


def position_for_layout(location, position):
    """Canonical position for ``location``, or ValidationError.

    * grid: must be a slot inside rows x columns (``b07`` becomes ``B7``);
    * named compartments: must be one of the names (spelling normalised);
    * free (or no layout): kept as typed.
    """
    layout = layout_of(location)

    if layout is None or layout.organization == "free":
        return position

    if layout.organization == "slots":
        wanted = " ".join(str(position).split()).lower()

        for name in layout.slot_labels or []:
            if name.lower() == wanted:
                return name

        raise ValidationError(
            f"'{position}' is not a compartment of {location.name}. "
            "Choose one of: " + ", ".join(layout.slot_labels or []) + "."
        )

    match = _GRID.match(str(position).strip())

    if match:
        row = ord(match.group(1).upper()) - 65
        column = int(match.group(2))

        if row < layout.rows and column <= layout.columns:
            return match.group(1).upper() + str(column)

    last = chr(64 + layout.rows) + str(layout.columns)

    raise ValidationError(
        f"'{position}' is outside the grid of {location.name} "
        f"(A1 to {last})."
    )
