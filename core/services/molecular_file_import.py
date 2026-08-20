from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
import re
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


MAX_MOLECULAR_IMPORT_BYTES = 20 * 1024 * 1024
MAX_IMPORTED_FEATURES = 5000

SUPPORTED_EXTENSIONS = {
    ".dna",
    ".gb",
    ".gbk",
    ".gbff",
    ".genbank",
    ".ape",
    ".embl",
    ".fa",
    ".fasta",
    ".fna",
    ".ffn",
    ".faa",
    ".frn",
    ".txt",
}

FORMAT_LABELS = {
    "snapgene": "SnapGene DNA",
    "genbank": "GenBank",
    "embl": "EMBL",
    "fasta": "FASTA",
    "raw": "Raw sequence",
}

SEQUENCE_TYPE_LABELS = {
    "dna": "DNA",
    "rna": "RNA",
    "protein": "Protein",
    "plasmid": "Plasmid",
    "primer": "Primer",
    "insert": "Insert",
    "other": "Other",
}

FEATURE_COLORS = {
    "promoter": "#F39C12",
    "rbs": "#3498DB",
    "cds": "#4F46E5",
    "terminator": "#E84393",
    "ori": "#E74C3C",
    "antibiotic": "#C0392B",
    "primer": "#00B894",
    "domain": "#8E44AD",
    "utr": "#1ABC9C",
    "custom": "#95A5A6",
}

NAMED_COLORS = {
    "black": "#212529",
    "red": "#E74C3C",
    "orange": "#F39C12",
    "green": "#27AE60",
    "blue": "#3498DB",
    "purple": "#8E44AD",
    "gray": "#95A5A6",
    "grey": "#95A5A6",
    "yellow": "#F1C40F",
    "pink": "#E84393",
    "cyan": "#00CEC9",
}


class MolecularFileImportError(ValueError):
    """Raised when an uploaded molecular file cannot be imported."""


def _json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    return str(value)


def _qualifier_values(
    qualifiers: dict[str, Any],
    key: str,
) -> list[str]:
    for candidate, value in qualifiers.items():
        if str(candidate).lower() != key.lower():
            continue

        if isinstance(
            value,
            (list, tuple),
        ):
            return [
                str(item)
                for item in value
                if item is not None
            ]

        if value is None:
            return []

        return [str(value)]

    return []


def _first_qualifier(
    qualifiers: dict[str, Any],
    *keys: str,
) -> str:
    for key in keys:
        for value in _qualifier_values(
            qualifiers,
            key,
        ):
            cleaned = value.strip()

            if cleaned:
                return cleaned

    return ""


def _raw_sequence_record(
    raw_data: bytes,
    filename: str,
) -> SeqRecord:
    text = raw_data.decode(
        "utf-8-sig",
        errors="replace",
    )

    sequence = re.sub(
        r"\s+",
        "",
        text,
    ).upper()

    if not sequence:
        raise MolecularFileImportError(
            "The text file contains no sequence."
        )

    if not re.fullmatch(
        r"[A-Z*?.-]+",
        sequence,
    ):
        raise MolecularFileImportError(
            "The text file is not a plain molecular sequence."
        )

    return SeqRecord(
        Seq(sequence),
        id=Path(filename).stem or "sequence",
        name=Path(filename).stem or "sequence",
        description="",
    )


def _candidate_formats(
    filename: str,
    raw_data: bytes,
) -> list[str]:
    suffix = Path(filename).suffix.lower()

    explicit = {
        ".dna": ["snapgene"],
        ".gb": ["genbank"],
        ".gbk": ["genbank"],
        ".gbff": ["genbank"],
        ".genbank": ["genbank"],
        ".ape": ["genbank"],
        ".embl": ["embl"],
        ".fa": ["fasta"],
        ".fasta": ["fasta"],
        ".fna": ["fasta"],
        ".ffn": ["fasta"],
        ".faa": ["fasta"],
        ".frn": ["fasta"],
    }

    if suffix in explicit:
        return explicit[suffix]

    stripped = raw_data.lstrip()

    if stripped.startswith(b"LOCUS"):
        return ["genbank"]

    if stripped.startswith(b"ID "):
        return ["embl"]

    if stripped.startswith(b">"):
        return ["fasta"]

    if suffix == ".txt":
        return [
            "genbank",
            "embl",
            "fasta",
            "raw",
        ]

    raise MolecularFileImportError(
        "Unsupported molecular file type. Supported extensions: "
        + ", ".join(
            sorted(SUPPORTED_EXTENSIONS)
        )
    )


def _read_record(
    raw_data: bytes,
    filename: str,
):
    errors: list[str] = []

    for file_format in _candidate_formats(
        filename,
        raw_data,
    ):
        try:
            if file_format == "raw":
                return (
                    _raw_sequence_record(
                        raw_data,
                        filename,
                    ),
                    "raw",
                )

            if file_format == "snapgene":
                handle = BytesIO(raw_data)
            else:
                text = raw_data.decode(
                    "utf-8-sig",
                    errors="replace",
                )
                handle = StringIO(text)

            record = SeqIO.read(
                handle,
                file_format,
            )

            if not str(record.seq):
                raise MolecularFileImportError(
                    "The molecular file contains an empty sequence."
                )

            return record, file_format

        except MolecularFileImportError:
            raise

        except Exception as exc:
            errors.append(
                f"{file_format}: {exc}"
            )

    raise MolecularFileImportError(
        "The file could not be parsed as a supported "
        "single-record molecular file. "
        + " | ".join(errors)
    )


def _record_name(
    record,
    filename: str,
) -> str:
    candidates = (
        getattr(record, "name", ""),
        getattr(record, "id", ""),
        Path(filename).stem,
    )

    for candidate in candidates:
        value = str(candidate or "").strip()

        if not value:
            continue

        if value.lower().startswith(
            "<unknown"
        ):
            continue

        if value == ".":
            continue

        return value[:255]

    return "Imported molecular sequence"


def _record_description(record) -> str:
    value = str(
        getattr(
            record,
            "description",
            "",
        )
        or ""
    ).strip()

    if value.lower().startswith(
        "<unknown"
    ):
        return ""

    record_id = str(
        getattr(record, "id", "")
        or ""
    ).strip()

    if value == record_id:
        return ""

    return value


def _topology(record) -> str:
    value = str(
        record.annotations.get(
            "topology",
            "",
        )
        or ""
    ).strip().lower()

    return (
        "circular"
        if value == "circular"
        else "linear"
    )


def _sequence_type(
    record,
    filename: str,
    topology: str,
) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix == ".faa":
        return "protein"

    if suffix == ".frn":
        return "rna"

    molecule_type = str(
        record.annotations.get(
            "molecule_type",
            "",
        )
        or ""
    ).lower()

    sequence = str(record.seq).upper()

    if "protein" in molecule_type:
        return "protein"

    if "rna" in molecule_type:
        return "rna"

    nucleotide_symbols = set(
        "ACGTURYSWKMBDHVNX.-"
    )

    if not set(sequence) <= nucleotide_symbols:
        return "protein"

    if "U" in sequence and "T" not in sequence:
        return "rna"

    if topology == "circular":
        return "plasmid"

    return "dna"



# ============================================================
# MOLECULAR_TYPE_AWARE_IMPORT_U1
# ============================================================


def _strip_leading_fasta_comments(
    raw_data: bytes,
    filename: str,
) -> bytes:
    """
    Normalize a legacy FASTA file containing explicit comment
    lines before the first > header.

    Only blank lines and lines beginning with #, ; or ! are
    removed. Arbitrary pre-header data is never discarded.
    """

    suffix = Path(
        filename
    ).suffix.lower()

    if suffix not in {
        ".fa",
        ".fasta",
        ".fna",
        ".ffn",
        ".faa",
        ".frn",
        ".txt",
    }:
        return raw_data

    text = raw_data.decode(
        "utf-8-sig",
        errors="replace",
    )

    lines = text.splitlines(
        keepends=True,
    )

    header_index = None

    for index, line in enumerate(
        lines
    ):
        if line.lstrip().startswith(
            ">"
        ):
            header_index = index
            break

    if (
        header_index is None
        or header_index == 0
    ):
        return raw_data

    prefix = lines[
        :header_index
    ]

    if not all(
        (
            not line.strip()
            or line.lstrip().startswith(
                (
                    "#",
                    ";",
                    "!",
                )
            )
        )
        for line in prefix
    ):
        return raw_data

    normalized = "".join(
        lines[
            header_index:
        ]
    )

    return normalized.encode(
        "utf-8"
    )


def _plain_text_sequence_record(
    raw_data: bytes,
    filename: str,
) -> SeqRecord | None:
    """
    Recognize an unstructured .txt sequence before the generic
    parser cascade reaches Bio.SeqIO's FASTA parser.
    """

    if (
        Path(filename).suffix.lower()
        != ".txt"
    ):
        return None

    text = raw_data.decode(
        "utf-8-sig",
        errors="replace",
    )

    if ">" in text:
        return None

    compact = re.sub(
        r"\s+",
        "",
        text,
    ).upper()

    if not compact:
        return None

    if not re.fullmatch(
        r"[A-Z*?.-]+",
        compact,
    ):
        return None

    return _raw_sequence_record(
        raw_data,
        filename,
    )


def _import_detection(
    record,
    filename: str,
    topology: str,
    sequence_type: str,
) -> dict[str, Any]:
    """
    Describe detected molecular content independently from the
    biological record type chosen by the user.

    Primer and Insert are never inferred solely from sequence.
    """

    suffix = Path(
        filename
    ).suffix.lower()

    molecule_type = str(
        record.annotations.get(
            "molecule_type",
            "",
        )
        or ""
    ).strip().lower()

    sequence = str(
        record.seq
    ).upper()

    nucleotide_symbols = set(
        "ACGTURYSWKMBDHVNX.-"
    )

    is_nucleotide = (
        set(sequence)
        <= nucleotide_symbols
    )

    has_t = "T" in sequence
    has_u = "U" in sequence

    compatible: list[str] = []

    if (
        sequence_type == "protein"
        or not is_nucleotide
    ):
        detected_content = "protein"

        detected_content_label = (
            "Protein sequence"
        )

        suggested = "protein"

        compatible = [
            "protein",
            "other",
        ]

        confidence = "strong"

        if suffix == ".faa":
            reason = (
                "The .faa extension explicitly identifies "
                "an amino-acid FASTA file."
            )

        elif "protein" in molecule_type:
            reason = (
                "The source record declares a protein "
                "molecule type."
            )

        else:
            reason = (
                "The sequence contains symbols outside "
                "the nucleotide alphabet."
            )

    else:
        if not has_u:
            compatible.extend(
                [
                    "dna",
                    "plasmid",
                    "primer",
                    "insert",
                ]
            )

        if not has_t:
            compatible.append(
                "rna"
            )

        compatible.append(
            "other"
        )

        if (
            suffix == ".frn"
            or "rna" in molecule_type
            or (
                has_u
                and not has_t
            )
        ):
            detected_content = "rna"

            detected_content_label = (
                "RNA-like nucleotide sequence"
            )

            suggested = "rna"
            confidence = "strong"

            if "rna" not in compatible:
                compatible.insert(
                    0,
                    "rna",
                )

            if suffix == ".frn":
                reason = (
                    "The .frn extension explicitly identifies "
                    "an RNA FASTA file."
                )

            elif "rna" in molecule_type:
                reason = (
                    "The source record declares an RNA "
                    "molecule type."
                )

            else:
                reason = (
                    "The sequence contains U and no T, "
                    "which is consistent with RNA."
                )

        elif topology == "circular":
            detected_content = "nucleotide"

            detected_content_label = (
                "Nucleotide sequence"
            )

            suggested = "plasmid"
            confidence = "strong"

            reason = (
                "The source record explicitly describes "
                "a circular nucleotide molecule."
            )

        else:
            detected_content = "nucleotide"

            detected_content_label = (
                "Nucleotide sequence"
            )

            suggested = (
                sequence_type
                if sequence_type
                in {
                    "dna",
                    "plasmid",
                    "rna",
                    "primer",
                    "insert",
                }
                else "dna"
            )

            confidence = "ambiguous"

            reason = (
                "A linear nucleotide sequence does not "
                "uniquely identify whether the biological "
                "record is DNA, RNA, a plasmid, a primer "
                "or an insert."
            )

    compatible = list(
        dict.fromkeys(
            compatible
        )
    )

    if suggested not in compatible:
        compatible.insert(
            0,
            suggested,
        )

    return {
        "detected_content": (
            detected_content
        ),
        "detected_content_label": (
            detected_content_label
        ),
        "suggested_sequence_type": (
            suggested
        ),
        "suggested_sequence_type_label": (
            SEQUENCE_TYPE_LABELS.get(
                suggested,
                suggested.title(),
            )
        ),
        "detection_confidence": (
            confidence
        ),
        "detection_confidence_label": (
            "Strong suggestion"
            if confidence == "strong"
            else "Needs confirmation"
        ),
        "detection_reason": reason,
        "requires_type_confirmation": (
            confidence == "ambiguous"
        ),
        "compatible_sequence_types": (
            compatible
        ),
    }


def _normalized_hex_color(
    value: str,
) -> str | None:
    cleaned = str(value or "").strip()

    match = re.search(
        r"#[0-9A-Fa-f]{6}",
        cleaned,
    )

    if match:
        return match.group(0).upper()

    return NAMED_COLORS.get(
        cleaned.lower().strip(
            " ;,.:"
        )
    )


def _feature_color(
    qualifiers: dict[str, Any],
) -> str | None:
    direct_keys = (
        "color",
        "ApEinfo_fwdcolor",
        "ApEinfo_revcolor",
        "fwdcolor",
        "revcolor",
    )

    for key in direct_keys:
        for value in _qualifier_values(
            qualifiers,
            key,
        ):
            color = _normalized_hex_color(
                value
            )

            if color:
                return color

    for note in _qualifier_values(
        qualifiers,
        "note",
    ):
        match = re.search(
            r"\bcolor\s*:\s*"
            r"(#[0-9A-Fa-f]{6}|"
            r"black|red|orange|green|blue|purple|"
            r"gray|grey|yellow|pink|cyan)",
            note,
            flags=re.IGNORECASE,
        )

        if match:
            color = _normalized_hex_color(
                match.group(1)
            )

            if color:
                return color

        segment_color = re.search(
            r"#[0-9A-Fa-f]{6}",
            note,
        )

        if (
            segment_color
            and "segment" in note.lower()
        ):
            return (
                segment_color
                .group(0)
                .upper()
            )

    return None


def _feature_name(
    original_type: str,
    qualifiers: dict[str, Any],
    index: int,
) -> str:
    value = _first_qualifier(
        qualifiers,
        "label",
        "gene",
        "locus_tag",
        "product",
        "name",
        "standard_name",
    )

    if not value:
        for note in _qualifier_values(
            qualifiers,
            "note",
        ):
            cleaned = note.strip()

            if not cleaned:
                continue

            if re.fullmatch(
                r"(?is).*"
                r"(?:color|direction|sequence|added)\s*:.*",
                cleaned,
            ):
                continue

            if "segments:" in cleaned.lower():
                continue

            value = cleaned.splitlines()[0]
            break

    if not value:
        value = (
            original_type
            .replace("_", " ")
            .strip()
            or f"Feature {index + 1}"
        )

    return value[:255]


def _feature_notes(
    qualifiers: dict[str, Any],
) -> str:
    notes: list[str] = []

    for note in _qualifier_values(
        qualifiers,
        "note",
    ):
        cleaned = note.strip()

        if not cleaned:
            continue

        if re.fullmatch(
            r"(?is)\s*"
            r"(?:color|direction|sequence|added)\s*:.*",
            cleaned,
        ):
            continue

        notes.append(cleaned)

    return "\n".join(notes)


def _mapped_feature_type(
    original_type: str,
    name: str,
    qualifiers: dict[str, Any],
) -> str:
    normalized = (
        str(original_type or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace("'", "")
    )

    text = " ".join(
        (
            normalized,
            name,
            _first_qualifier(
                qualifiers,
                "product",
                "gene",
                "label",
                "note",
            ),
        )
    ).lower()

    direct = {
        "promoter": "promoter",
        "rbs": "rbs",
        "ribosome_binding_site": "rbs",
        "cds": "cds",
        "gene": "cds",
        "terminator": "terminator",
        "rep_origin": "ori",
        "origin_of_replication": "ori",
        "primer_bind": "primer",
        "primer": "primer",
        "5utr": "utr",
        "3utr": "utr",
        "utr": "utr",
        "protein_bind": "domain",
        "mat_peptide": "domain",
        "domain": "domain",
        "region": "domain",
        "misc_feature": "custom",
        "misc_binding": "custom",
        "regulatory": "custom",
    }

    antibiotic_markers = (
        "antibiotic",
        "resistance",
        "ampicillin",
        "kanamycin",
        "chloramphenicol",
        "tetracycline",
        "spectinomycin",
        "hygromycin",
        "blasticidin",
        "puromycin",
        "ampr",
        "kanr",
        "cmr",
        "tetr",
    )

    if any(
        marker in text
        for marker in antibiotic_markers
    ):
        return "antibiotic"

    return direct.get(
        normalized,
        "custom",
    )


def _location_payload(
    feature,
    sequence_length: int,
    circular: bool,
) -> tuple[
    int,
    int,
    str,
    list[dict[str, int]],
    dict[str, Any],
]:
    location = getattr(
        feature,
        "location",
        None,
    )

    if location is None:
        raise MolecularFileImportError(
            "A feature without coordinates was encountered."
        )

    parts = list(
        getattr(
            location,
            "parts",
            [location],
        )
    )

    segments: list[dict[str, int]] = []

    for part in parts:
        zero_start = int(part.start)
        zero_end = int(part.end)

        if zero_end <= zero_start:
            continue

        segments.append(
            {
                "start": zero_start + 1,
                "end": zero_end,
            }
        )

    if not segments:
        raise MolecularFileImportError(
            "A feature contains no usable coordinate segment."
        )

    wraps_origin = (
        circular
        and len(segments) > 1
        and any(
            segment["start"] == 1
            for segment in segments
        )
        and any(
            segment["end"] == sequence_length
            for segment in segments
        )
    )

    if wraps_origin:
        high_segment = max(
            segments,
            key=lambda segment: segment["start"],
        )
        low_segment = min(
            segments,
            key=lambda segment: segment["start"],
        )

        start = high_segment["start"]
        end = low_segment["end"]
    else:
        start = min(
            segment["start"]
            for segment in segments
        )
        end = max(
            segment["end"]
            for segment in segments
        )

    strand_number = getattr(
        location,
        "strand",
        None,
    )

    if strand_number == 1:
        strand = "+"
    elif strand_number == -1:
        strand = "-"
    else:
        strand = "."

    metadata = {
        "location": str(location),
        "operator": getattr(
            location,
            "operator",
            None,
        ),
        "wraps_origin": wraps_origin,
        "segments": segments,
    }

    return (
        start,
        end,
        strand,
        segments,
        metadata,
    )


def _feature_payload(
    feature,
    index: int,
    sequence_length: int,
    topology: str,
    source_format: str,
) -> tuple[dict[str, Any], list[str]]:
    original_type = str(
        getattr(
            feature,
            "type",
            "",
        )
        or "misc_feature"
    )

    qualifiers = {
        str(key): _json_safe(value)
        for key, value in (
            getattr(
                feature,
                "qualifiers",
                {},
            )
            or {}
        ).items()
    }

    (
        start,
        end,
        strand,
        segments,
        location_metadata,
    ) = _location_payload(
        feature,
        sequence_length,
        topology == "circular",
    )

    name = _feature_name(
        original_type,
        qualifiers,
        index,
    )

    mapped_type = _mapped_feature_type(
        original_type,
        name,
        qualifiers,
    )

    imported_color = _feature_color(
        qualifiers
    )

    qualifiers["biobank_import"] = {
        "source_format": source_format,
        "original_feature_type": original_type,
        **location_metadata,
    }

    qualifiers["biobank_auto_color"] = (
        imported_color is None
    )

    warnings: list[str] = []

    if len(segments) > 1:
        warnings.append(
            f'Feature "{name}" has {len(segments)} segments. '
            "Exact segments were preserved in qualifiers; "
            "the current editor displays an envelope or an "
            "origin-spanning interval."
        )

    return (
        {
            "name": name,
            "type": mapped_type,
            "start": start,
            "end": end,
            "strand": strand,
            "color": (
                imported_color
                or FEATURE_COLORS[mapped_type]
            ),
            "notes": _feature_notes(
                qualifiers
            ),
            "qualifiers": qualifiers,
            "order": index,
        },
        warnings,
    )


def parse_molecular_file(
    uploaded_file,
) -> dict[str, Any]:
    if uploaded_file is None:
        raise MolecularFileImportError(
            "No molecular file was provided."
        )

    filename = Path(
        str(
            getattr(
                uploaded_file,
                "name",
                "",
            )
            or "uploaded-molecule"
        )
    ).name

    raw_data = uploaded_file.read(
        MAX_MOLECULAR_IMPORT_BYTES + 1
    )

    if not raw_data:
        raise MolecularFileImportError(
            "The uploaded molecular file is empty."
        )

    if len(raw_data) > MAX_MOLECULAR_IMPORT_BYTES:
        raise MolecularFileImportError(
            "The uploaded molecular file exceeds the 20 MiB limit."
        )

    raw_data = _strip_leading_fasta_comments(
        raw_data,
        filename,
    )

    plain_record = _plain_text_sequence_record(
        raw_data,
        filename,
    )

    if plain_record is not None:
        record = plain_record
        source_format = "raw"

    else:
        record, source_format = _read_record(
            raw_data,
            filename,
        )

    sequence = (
        str(record.seq)
        .replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .upper()
    )

    topology = _topology(record)

    sequence_type = _sequence_type(
        record,
        filename,
        topology,
    )

    detection = _import_detection(
        record,
        filename,
        topology,
        sequence_type,
    )

    source_features = list(
        getattr(
            record,
            "features",
            [],
        )
        or []
    )

    if len(source_features) > MAX_IMPORTED_FEATURES:
        raise MolecularFileImportError(
            "The molecular file contains more than "
            f"{MAX_IMPORTED_FEATURES} annotations."
        )

    warnings: list[str] = []
    features: list[dict[str, Any]] = []

    for index, feature in enumerate(
        source_features
    ):
        if str(
            getattr(
                feature,
                "type",
                "",
            )
        ).lower() == "source":
            continue

        try:
            payload, feature_warnings = (
                _feature_payload(
                    feature,
                    index,
                    len(sequence),
                    topology,
                    source_format,
                )
            )
        except MolecularFileImportError as exc:
            warnings.append(
                f"Skipped feature {index + 1}: {exc}"
            )
            continue

        payload["order"] = len(features)

        features.append(payload)
        warnings.extend(feature_warnings)

    metadata = {
        str(key): _json_safe(value)
        for key, value in (
            getattr(
                record,
                "annotations",
                {},
            )
            or {}
        ).items()
    }

    return {
        "source_filename": filename,
        "format": source_format,
        "format_label": FORMAT_LABELS[
            source_format
        ],
        "name": _record_name(
            record,
            filename,
        ),
        "description": _record_description(
            record
        ),
        "sequence_type": sequence_type,
        "sequence_type_label": (
            SEQUENCE_TYPE_LABELS[
                sequence_type
            ]
        ),
        "detected_content": (
            detection[
                "detected_content"
            ]
        ),
        "detected_content_label": (
            detection[
                "detected_content_label"
            ]
        ),
        "suggested_sequence_type": (
            detection[
                "suggested_sequence_type"
            ]
        ),
        "suggested_sequence_type_label": (
            detection[
                "suggested_sequence_type_label"
            ]
        ),
        "detection_confidence": (
            detection[
                "detection_confidence"
            ]
        ),
        "detection_confidence_label": (
            detection[
                "detection_confidence_label"
            ]
        ),
        "detection_reason": (
            detection[
                "detection_reason"
            ]
        ),
        "requires_type_confirmation": (
            detection[
                "requires_type_confirmation"
            ]
        ),
        "compatible_sequence_types": (
            detection[
                "compatible_sequence_types"
            ]
        ),
        "topology": topology,
        "sequence": sequence,
        "length": len(sequence),
        "features": features,
        "feature_count": len(features),
        "warnings": warnings,
        "metadata": metadata,
    }
