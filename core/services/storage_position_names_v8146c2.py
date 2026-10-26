"""Position names used by the physical storage assignment services."""

import re
import unicodedata

from django.core.exceptions import ValidationError


def normalize_physical_position_v8146c2(value):
    """Preserve user spelling and reject invalid position identifiers."""
    position = str(value or "").strip()

    if not 1 <= len(position) <= 100:
        raise ValidationError(
            "Position name must contain 1 to 100 characters."
        )

    if any(char in position for char in (">", ";", ",")):
        raise ValidationError(
            "Position name cannot contain >, commas or semicolons."
        )

    if any(
        unicodedata.category(char).startswith("C")
        for char in position
    ):
        raise ValidationError(
            "Position name cannot contain control characters."
        )

    # Preserve the historical uppercase convention for
    # alphanumeric position codes such as A1 and P03.
    # Keep descriptive user-defined names unchanged.
    if re.fullmatch(r"[A-Za-z]+[0-9]+", position):
        return position.upper()

    return position
