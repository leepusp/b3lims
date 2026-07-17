import re


class MolecularSequenceInputError(ValueError):
    """Raised when molecular sequence or feature input is invalid."""


SEQUENCE_ALPHABETS = {
    "dna": set("ACGTRYSWKMBDHVN"),
    "plasmid": set("ACGTRYSWKMBDHVN"),
    "primer": set("ACGTRYSWKMBDHVN"),
    "insert": set("ACGTRYSWKMBDHVN"),
    "rna": set("ACGURYSWKMBDHVN"),
    "protein": set("ACDEFGHIKLMNPQRSTVWYBXZJUO*"),
    "other": set("ABCDEFGHIJKLMNOPQRSTUVWXYZ*.-"),
}

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_molecular_sequence(raw_sequence, sequence_type):
    """
    Normalize one raw or FASTA-formatted molecular sequence and validate its
    alphabet. Multiple FASTA records are intentionally rejected.
    """
    text = str(raw_sequence or "").strip()
    lines = text.splitlines()

    headers = [line for line in lines if line.lstrip().startswith(">")]
    if len(headers) > 1:
        raise MolecularSequenceInputError(
            "Only one FASTA record may be stored in a Molecular Item."
        )

    sequence_lines = [
        line
        for line in lines
        if not line.lstrip().startswith(">")
    ]

    sequence = "".join(sequence_lines)
    sequence = "".join(sequence.split()).upper()

    if not sequence:
        raise MolecularSequenceInputError("Sequence is required.")

    allowed = SEQUENCE_ALPHABETS.get(sequence_type)
    if allowed is None:
        raise MolecularSequenceInputError("Unsupported sequence type.")

    invalid = sorted(set(sequence) - allowed)
    if invalid:
        invalid_display = ", ".join(repr(character) for character in invalid)
        raise MolecularSequenceInputError(
            f"Invalid character(s) for {sequence_type}: {invalid_display}."
        )

    return sequence


def validate_molecular_feature(item, molecule, order):
    """Validate and normalize one structured MolecularFeature payload."""
    if not isinstance(item, dict):
        raise MolecularSequenceInputError(
            f"Feature {order + 1} must be an object."
        )

    sequence_length = molecule.length
    if sequence_length < 1:
        raise MolecularSequenceInputError(
            "Features cannot be added to an empty sequence."
        )

    name = str(item.get("name") or "").strip()
    if not name:
        raise MolecularSequenceInputError(
            f"Feature {order + 1} requires a name."
        )

    feature_type = (
        item.get("type")
        or item.get("feature_type")
        or "custom"
    )
    valid_types = {
        choice[0]
        for choice in molecule.features.model.FEATURE_TYPES
    }

    if feature_type not in valid_types:
        raise MolecularSequenceInputError(
            f"Feature {order + 1} has an invalid type."
        )

    try:
        start = int(item.get("start"))
        end = int(item.get("end"))
    except (TypeError, ValueError):
        raise MolecularSequenceInputError(
            f"Feature {order + 1} requires integer coordinates."
        )

    if not 1 <= start <= sequence_length:
        raise MolecularSequenceInputError(
            f"Feature {order + 1} start must be between 1 and "
            f"{sequence_length}."
        )

    if not 1 <= end <= sequence_length:
        raise MolecularSequenceInputError(
            f"Feature {order + 1} end must be between 1 and "
            f"{sequence_length}."
        )

    if start > end and molecule.topology != "circular":
        raise MolecularSequenceInputError(
            f"Feature {order + 1} crosses the origin, but the sequence "
            "is not circular."
        )

    strand = item.get("strand") or "+"
    if strand not in {"+", "-", "."}:
        raise MolecularSequenceInputError(
            f"Feature {order + 1} has an invalid strand."
        )

    color = str(item.get("color") or "#868e96")
    if not HEX_COLOR_RE.fullmatch(color):
        raise MolecularSequenceInputError(
            f"Feature {order + 1} has an invalid color."
        )

    qualifiers = (
        item.get("qualifiers")
        or item.get("qualifiers_json")
        or {}
    )
    if not isinstance(qualifiers, dict):
        raise MolecularSequenceInputError(
            f"Feature {order + 1} qualifiers must be an object."
        )

    return {
        "name": name[:255],
        "feature_type": feature_type,
        "start": start,
        "end": end,
        "strand": strand,
        "color": color,
        "notes": str(item.get("notes") or ""),
        "qualifiers_json": qualifiers,
        "order": order,
    }
