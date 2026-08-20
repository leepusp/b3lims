from __future__ import annotations

from collections.abc import Iterable

from Bio.Restriction import (
    AllEnzymes,
    Analysis,
    CommOnly,
    RestrictionBatch,
)
from Bio.Seq import Seq


MAX_RESTRICTION_SEQUENCE_LENGTH = 2_000_000
MAX_SELECTED_ENZYMES = 256
MAX_RETURNED_SITES = 20_000

MIN_RECOGNITION_LENGTH = 4
MAX_RECOGNITION_LENGTH = 32

VALID_MODES = {
    "none",
    "unique",
    "selected",
    "common",
    "all",
}

VALID_CATALOGS = {
    "common",
    "all",
}

DNA_IUPAC_SYMBOLS = set(
    "ACGTRYSWKMBDHVN"
)


class MolecularRestrictionSiteError(ValueError):
    """Invalid molecular restriction analysis request."""


_ENZYME_BY_NAME = {
    str(enzyme): enzyme
    for enzyme in AllEnzymes
}

_CANONICAL_NAME_BY_CASEFOLD = {
    name.casefold(): name
    for name in _ENZYME_BY_NAME
}

_COMMON_ENZYME_NAMES = {
    str(enzyme)
    for enzyme in CommOnly
}


def _clean_dna_sequence(sequence: object) -> str:
    cleaned = "".join(
        str(sequence or "").split()
    ).upper()

    if len(cleaned) > MAX_RESTRICTION_SEQUENCE_LENGTH:
        raise MolecularRestrictionSiteError(
            (
                "Restriction-site analysis is limited to "
                f"{MAX_RESTRICTION_SEQUENCE_LENGTH:,} bp."
            )
        )

    invalid = sorted(
        set(cleaned)
        - DNA_IUPAC_SYMBOLS
    )

    if invalid:
        display = ", ".join(
            repr(symbol)
            for symbol in invalid[:10]
        )

        raise MolecularRestrictionSiteError(
            (
                "Restriction-site analysis supports IUPAC DNA "
                f"symbols only. Invalid symbol(s): {display}."
            )
        )

    return cleaned


def _normalize_minimum_site_length(value: object) -> int:
    try:
        minimum = int(value)
    except (TypeError, ValueError) as exc:
        raise MolecularRestrictionSiteError(
            "minimum_site_length must be an integer."
        ) from exc

    if not (
        MIN_RECOGNITION_LENGTH
        <= minimum
        <= MAX_RECOGNITION_LENGTH
    ):
        raise MolecularRestrictionSiteError(
            (
                "minimum_site_length must be between "
                f"{MIN_RECOGNITION_LENGTH} and "
                f"{MAX_RECOGNITION_LENGTH}."
            )
        )

    return minimum


def _canonical_selected_names(
    selected_enzymes: object,
) -> list[str]:
    if selected_enzymes is None:
        return []

    if isinstance(selected_enzymes, str):
        selected_enzymes = [selected_enzymes]

    if not isinstance(selected_enzymes, Iterable):
        raise MolecularRestrictionSiteError(
            "selected_enzymes must be a list of enzyme names."
        )

    raw_names = [
        str(name).strip()
        for name in selected_enzymes
        if str(name).strip()
    ]

    if len(raw_names) > MAX_SELECTED_ENZYMES:
        raise MolecularRestrictionSiteError(
            (
                f"At most {MAX_SELECTED_ENZYMES} enzymes "
                "may be selected in one request."
            )
        )

    canonical_names = []
    unknown = []

    for name in raw_names:
        canonical = (
            _CANONICAL_NAME_BY_CASEFOLD.get(
                name.casefold()
            )
        )

        if canonical is None:
            unknown.append(name)
        else:
            canonical_names.append(canonical)

    if unknown:
        shown = ", ".join(unknown[:10])

        if len(unknown) > 10:
            shown += ", ..."

        raise MolecularRestrictionSiteError(
            f"Unknown restriction enzyme(s): {shown}."
        )

    return sorted(
        set(canonical_names)
    )


def _overhang_type(enzyme) -> str:
    if enzyme.is_blunt():
        return "blunt"

    if enzyme.is_5overhang():
        return "5_prime"

    if enzyme.is_3overhang():
        return "3_prime"

    return "unknown"


def _enzyme_metadata(enzyme) -> dict:
    name = str(enzyme)
    recognition_sequence = str(enzyme.site)

    return {
        "name": name,
        "recognition_sequence": recognition_sequence,
        "recognition_length": len(recognition_sequence),
        "commercial_common": (
            name in _COMMON_ENZYME_NAMES
        ),
        "overhang_type": _overhang_type(enzyme),
        "overhang_length": abs(
            int(enzyme.ovhg or 0)
        ),
        "fst5": (
            None
            if enzyme.fst5 is None
            else int(enzyme.fst5)
        ),
        "fst3": (
            None
            if enzyme.fst3 is None
            else int(enzyme.fst3)
        ),
    }


def _candidate_enzymes(
    *,
    mode: str,
    catalog: str,
    minimum_site_length: int,
    selected_names: list[str],
):
    if mode == "none":
        return []

    if mode == "selected":
        return [
            _ENZYME_BY_NAME[name]
            for name in selected_names
        ]

    source = (
        CommOnly
        if catalog == "common"
        else AllEnzymes
    )

    return sorted(
        (
            enzyme
            for enzyme in source
            if len(str(enzyme.site))
            >= minimum_site_length
        ),
        key=str,
    )


def _normalize_positions(
    positions,
    *,
    sequence_length: int,
    circular: bool,
) -> list[int]:
    normalized = []

    for raw_position in positions:
        position = int(raw_position)

        if circular and sequence_length:
            position = (
                ((position - 1) % sequence_length)
                + 1
            )

        normalized.append(position)

    return sorted(
        set(normalized)
    )


def restriction_enzyme_metadata(
    enzyme_names: Iterable[str],
) -> list[dict]:
    canonical_names = (
        _canonical_selected_names(
            list(enzyme_names)
        )
    )

    return [
        _enzyme_metadata(
            _ENZYME_BY_NAME[name]
        )
        for name in canonical_names
    ]


def analyze_restriction_sites(
    sequence: object,
    *,
    topology: str = "linear",
    mode: str = "unique",
    catalog: str = "common",
    minimum_site_length: object = 6,
    selected_enzymes: object = None,
) -> dict:
    cleaned = _clean_dna_sequence(sequence)

    topology = str(
        topology or "linear"
    ).strip().lower()

    if topology not in {
        "linear",
        "circular",
    }:
        raise MolecularRestrictionSiteError(
            "topology must be linear or circular."
        )

    requested_mode = str(
        mode or "unique"
    ).strip().lower()

    catalog = str(
        catalog or "common"
    ).strip().lower()

    if requested_mode not in VALID_MODES:
        raise MolecularRestrictionSiteError(
            (
                "mode must be one of: "
                "none, unique, selected, common, all."
            )
        )

    if catalog not in VALID_CATALOGS:
        raise MolecularRestrictionSiteError(
            "catalog must be common or all."
        )

    mode = requested_mode

    # Compatibility with the existing workspace control.
    if mode == "common":
        mode = "all"
        catalog = "common"

    minimum = (
        _normalize_minimum_site_length(
            minimum_site_length
        )
    )

    selected_names = (
        _canonical_selected_names(
            selected_enzymes
        )
    )

    candidates = _candidate_enzymes(
        mode=mode,
        catalog=catalog,
        minimum_site_length=minimum,
        selected_names=selected_names,
    )

    if not cleaned or not candidates:
        return {
            "sequence_length": len(cleaned),
            "topology": topology,
            "circular": topology == "circular",
            "requested_mode": requested_mode,
            "mode": mode,
            "catalog": catalog,
            "minimum_site_length": minimum,
            "candidate_enzyme_count": len(candidates),
            "cutting_enzyme_count": 0,
            "unique_cutter_count": 0,
            "site_count": 0,
            "enzymes": [],
            "sites": [],
        }

    circular = topology == "circular"

    analysis = Analysis(
        RestrictionBatch(candidates),
        Seq(cleaned),
        linear=not circular,
    )

    raw_results = analysis.full()

    enzyme_rows = []

    for enzyme in sorted(
        raw_results,
        key=str,
    ):
        positions = _normalize_positions(
            raw_results[enzyme],
            sequence_length=len(cleaned),
            circular=circular,
        )

        if not positions:
            continue

        if (
            mode == "unique"
            and len(positions) != 1
        ):
            continue

        metadata = _enzyme_metadata(enzyme)

        enzyme_rows.append(
            {
                **metadata,
                "positions": positions,
                "site_count": len(positions),
                "unique": len(positions) == 1,
            }
        )

    total_sites = sum(
        item["site_count"]
        for item in enzyme_rows
    )

    if total_sites > MAX_RETURNED_SITES:
        raise MolecularRestrictionSiteError(
            (
                "Restriction analysis produced "
                f"{total_sites:,} sites, exceeding the "
                f"{MAX_RETURNED_SITES:,}-site display limit. "
                "Increase minimum_site_length or use "
                "unique or selected mode."
            )
        )

    sites = []

    for enzyme_row in enzyme_rows:
        for position in enzyme_row["positions"]:
            sites.append(
                {
                    "enzyme": enzyme_row["name"],
                    "position": position,
                    "label": (
                        f"{enzyme_row['name']} "
                        f"({position})"
                    ),
                    "recognition_sequence": (
                        enzyme_row[
                            "recognition_sequence"
                        ]
                    ),
                    "recognition_length": (
                        enzyme_row[
                            "recognition_length"
                        ]
                    ),
                    "commercial_common": (
                        enzyme_row[
                            "commercial_common"
                        ]
                    ),
                    "site_count": (
                        enzyme_row[
                            "site_count"
                        ]
                    ),
                    "unique": enzyme_row["unique"],
                    "overhang_type": (
                        enzyme_row[
                            "overhang_type"
                        ]
                    ),
                    "overhang_length": (
                        enzyme_row[
                            "overhang_length"
                        ]
                    ),
                    "fst5": enzyme_row["fst5"],
                    "fst3": enzyme_row["fst3"],
                }
            )

    sites.sort(
        key=lambda item: (
            item["position"],
            item["enzyme"],
        )
    )

    return {
        "sequence_length": len(cleaned),
        "topology": topology,
        "circular": circular,
        "requested_mode": requested_mode,
        "mode": mode,
        "catalog": catalog,
        "minimum_site_length": minimum,
        "candidate_enzyme_count": len(candidates),
        "cutting_enzyme_count": len(enzyme_rows),
        "unique_cutter_count": sum(
            1
            for item in enzyme_rows
            if item["unique"]
        ),
        "site_count": total_sites,
        "enzymes": enzyme_rows,
        "sites": sites,
    }
