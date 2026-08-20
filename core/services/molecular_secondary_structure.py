from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


MAX_SECONDARY_STRUCTURE_FILE_BYTES = (
    2 * 1024 * 1024
)

DOT_BRACKET_SYMBOLS = frozenset(
    ".()"
)

_STRUCTURE_LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<structure>[().]+)
    (?:
        \s+
        \(
            \s*
            (?P<mfe>
                [+-]?
                (?:
                    \d+(?:\.\d*)?
                    |
                    \.\d+
                )
            )
            \s*
        \)
    )?
    \s*$
    """,
    re.VERBOSE,
)


class MolecularSecondaryStructureImportError(
    ValueError
):
    pass


def normalize_rna_sequence(
    sequence: str,
) -> str:
    return "".join(
        str(
            sequence
            or ""
        ).split()
    ).upper()


def checksum_secondary_structure_source(
    source_text: str,
) -> str:
    return hashlib.sha256(
        str(
            source_text
        ).encode(
            "utf-8"
        )
    ).hexdigest()


def validate_dot_bracket(
    structure: str,
    *,
    expected_length: int | None = None,
) -> dict:
    normalized = "".join(
        str(
            structure
            or ""
        ).split()
    )

    if not normalized:
        raise MolecularSecondaryStructureImportError(
            "Secondary structure is empty."
        )

    invalid = sorted(
        set(normalized)
        - DOT_BRACKET_SYMBOLS
    )

    if invalid:
        raise MolecularSecondaryStructureImportError(
            (
                "Unsupported dot-bracket symbols: "
                + " ".join(invalid)
                + ". R1B accepts only '.', '(' and ')'."
            )
        )

    if (
        expected_length is not None
        and len(normalized) != expected_length
    ):
        raise MolecularSecondaryStructureImportError(
            (
                "RNA sequence and secondary structure "
                "must have the same length "
                f"({expected_length} != {len(normalized)})."
            )
        )

    stack = []
    pairs = []

    for position, symbol in enumerate(
        normalized,
        start=1,
    ):
        if symbol == "(":
            stack.append(position)

        elif symbol == ")":
            if not stack:
                raise MolecularSecondaryStructureImportError(
                    (
                        "Unmatched ')' at secondary-structure "
                        f"position {position}."
                    )
                )

            left = stack.pop()

            pairs.append(
                (
                    left,
                    position,
                )
            )

    if stack:
        raise MolecularSecondaryStructureImportError(
            (
                "Unmatched '(' at secondary-structure "
                f"position {stack[-1]}."
            )
        )

    return {
        "structure": normalized,
        "length": len(normalized),
        "pair_count": len(pairs),
        "pairs": sorted(pairs),
    }


def _parse_structure_line(
    line: str,
) -> tuple[str, Decimal | None]:
    match = _STRUCTURE_LINE_RE.fullmatch(
        str(
            line
            or ""
        )
    )

    if match is None:
        raise MolecularSecondaryStructureImportError(
            (
                "Could not parse the secondary-structure line. "
                "Expected canonical dot-bracket notation, "
                "optionally followed by an explicit MFE "
                "such as '(((...))) (-1.20)'."
            )
        )

    structure = match.group(
        "structure"
    )

    mfe_text = match.group(
        "mfe"
    )

    minimum_free_energy = None

    if mfe_text is not None:
        try:
            minimum_free_energy = Decimal(
                mfe_text
            )
        except InvalidOperation as exc:
            raise MolecularSecondaryStructureImportError(
                "Invalid minimum free-energy value."
            ) from exc

    return (
        structure,
        minimum_free_energy,
    )


def parse_secondary_structure_source(
    source_text: str,
    *,
    molecule_sequence: str,
    filename: str = "",
) -> dict:
    if source_text is None:
        raise MolecularSecondaryStructureImportError(
            "No secondary-structure source was supplied."
        )

    source_text = str(
        source_text
    )

    if "\x00" in source_text:
        raise MolecularSecondaryStructureImportError(
            "Secondary-structure source contains a NUL byte."
        )

    if not source_text.strip():
        raise MolecularSecondaryStructureImportError(
            "Secondary-structure source is empty."
        )

    lines = [
        line.strip()
        for line in source_text.splitlines()
        if line.strip()
    ]

    target_sequence = normalize_rna_sequence(
        molecule_sequence
    )

    if not target_sequence:
        raise MolecularSecondaryStructureImportError(
            "The RNA record has no sequence."
        )

    source_sequence = None
    parsed_name = ""
    minimum_free_energy = None

    if lines[0].startswith(
        ">"
    ):
        if len(lines) < 3:
            raise MolecularSecondaryStructureImportError(
                (
                    "A DBN source requires a header, "
                    "RNA sequence and dot-bracket structure."
                )
            )

        parsed_name = lines[0][
            1:
        ].strip()

        (
            structure,
            minimum_free_energy,
        ) = _parse_structure_line(
            lines[-1]
        )

        source_sequence = normalize_rna_sequence(
            "".join(
                lines[1:-1]
            )
        )

        source_format = "dbn"

    elif len(lines) == 1:
        (
            structure,
            minimum_free_energy,
        ) = _parse_structure_line(
            lines[0]
        )

        if minimum_free_energy is not None:
            raise MolecularSecondaryStructureImportError(
                (
                    "An MFE cannot be associated with a "
                    "structure-only source because no source "
                    "RNA sequence was supplied."
                )
            )

        source_format = "dot_bracket"

    elif len(lines) == 2:
        source_sequence = normalize_rna_sequence(
            lines[0]
        )

        (
            structure,
            minimum_free_energy,
        ) = _parse_structure_line(
            lines[1]
        )

        source_format = (
            "rnafold"
            if minimum_free_energy is not None
            else "sequence_dot_bracket"
        )

    else:
        raise MolecularSecondaryStructureImportError(
            (
                "Unsupported RNA secondary-structure text layout. "
                "R1B accepts structure-only dot-bracket, "
                "simple DBN, or two-line sequence + structure text."
            )
        )

    if source_sequence is not None:
        if not source_sequence:
            raise MolecularSecondaryStructureImportError(
                "The supplied RNA sequence is empty."
            )

        if source_sequence != target_sequence:
            raise MolecularSecondaryStructureImportError(
                (
                    "The RNA sequence in the secondary-structure "
                    "source does not exactly match the current "
                    "MolecularSequence. No T/U conversion or "
                    "other sequence normalization is performed."
                )
            )

    validated = validate_dot_bracket(
        structure,
        expected_length=len(
            target_sequence
        ),
    )

    original_filename = (
        Path(filename).name
        if filename
        else ""
    )

    return {
        "name": parsed_name[:255],
        "structure": validated[
            "structure"
        ],
        "structure_length": validated[
            "length"
        ],
        "pair_count": validated[
            "pair_count"
        ],
        "pairs": validated[
            "pairs"
        ],
        "source_format": source_format,
        "minimum_free_energy": minimum_free_energy,
        "original_filename": original_filename[:255],
        "source_sequence_present": (
            source_sequence is not None
        ),
    }


def read_secondary_structure_upload(
    uploaded_file,
) -> dict:
    if uploaded_file is None:
        raise MolecularSecondaryStructureImportError(
            "No secondary-structure file was uploaded."
        )

    filename = Path(
        str(
            getattr(
                uploaded_file,
                "name",
                "",
            )
            or ""
        )
    ).name

    if not filename:
        raise MolecularSecondaryStructureImportError(
            "The uploaded source has no filename."
        )

    size = getattr(
        uploaded_file,
        "size",
        None,
    )

    if (
        size is not None
        and int(size)
        > MAX_SECONDARY_STRUCTURE_FILE_BYTES
    ):
        raise MolecularSecondaryStructureImportError(
            "The secondary-structure source exceeds 2 MiB."
        )

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    raw = uploaded_file.read(
        MAX_SECONDARY_STRUCTURE_FILE_BYTES
        + 1
    )

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    if not raw:
        raise MolecularSecondaryStructureImportError(
            "The uploaded secondary-structure file is empty."
        )

    if (
        len(raw)
        > MAX_SECONDARY_STRUCTURE_FILE_BYTES
    ):
        raise MolecularSecondaryStructureImportError(
            "The secondary-structure source exceeds 2 MiB."
        )

    try:
        source_text = raw.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError as exc:
        raise MolecularSecondaryStructureImportError(
            (
                "RNA secondary-structure sources "
                "must be UTF-8 text."
            )
        ) from exc

    return {
        "filename": filename,
        "source_text": source_text,
        "checksum_sha256": hashlib.sha256(
            raw
        ).hexdigest(),
    }
