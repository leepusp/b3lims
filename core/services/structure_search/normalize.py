from __future__ import annotations

from collections.abc import Iterable


def optional_float(
    value,
):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def optional_fraction(
    value,
):
    value = optional_float(
        value
    )

    if value is None:
        return None

    #
    # Provider APIs differ between [0, 1] fractions and
    # [0, 100] percentages. Internally use [0, 1].
    #
    if (
        value > 1.0
        and value <= 100.0
    ):
        value /= 100.0

    if (
        value < 0.0
        or value > 1.0
    ):
        return None

    return value


def string_tuple(
    values: Iterable | None,
) -> tuple[str, ...]:
    if values is None:
        return ()

    normalized = []

    for value in values:
        item = str(
            value
            or ""
        ).strip()

        if (
            item
            and item
            not in normalized
        ):
            normalized.append(
                item
            )

    return tuple(
        normalized
    )


def pdb_canonical_key(
    pdb_id,
    entity_id,
):
    pdb_id = str(
        pdb_id
        or ""
    ).strip().upper()

    entity_id = str(
        entity_id
        or ""
    ).strip()

    if not pdb_id:
        raise ValueError(
            "PDB identifier is required."
        )

    if not entity_id:
        raise ValueError(
            "PDB entity identifier is required."
        )

    return (
        f"pdb:{pdb_id}:{entity_id}"
    )
