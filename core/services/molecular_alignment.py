from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path

from Bio import AlignIO


MAX_ALIGNMENT_FILE_BYTES = 20 * 1024 * 1024
MAX_ALIGNMENT_SEQUENCES = 5000
MAX_ALIGNMENT_COLUMNS = 200000

SOURCE_FORMATS = {
    ".afa": (
        "fasta",
        "aligned_fasta",
        "Aligned FASTA",
    ),
    ".fa": (
        "fasta",
        "aligned_fasta",
        "Aligned FASTA",
    ),
    ".fasta": (
        "fasta",
        "aligned_fasta",
        "Aligned FASTA",
    ),
    ".aln": (
        "clustal",
        "clustal",
        "CLUSTAL",
    ),
    ".sto": (
        "stockholm",
        "stockholm",
        "Stockholm",
    ),
    ".stk": (
        "stockholm",
        "stockholm",
        "Stockholm",
    ),
}

DEFERRED_EXTENSIONS = {
    ".a2m",
    ".a3m",
    ".msa",
}

ALLOWED_RENDER_SYMBOLS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ*-?"
)


class MolecularAlignmentImportError(
    ValueError
):
    pass


def _read_uploaded_bytes(
    uploaded_file,
) -> tuple[str, bytes]:
    if uploaded_file is None:
        raise MolecularAlignmentImportError(
            "No alignment file was uploaded."
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
        raise MolecularAlignmentImportError(
            "The uploaded alignment has no filename."
        )

    size = getattr(
        uploaded_file,
        "size",
        None,
    )

    if (
        size is not None
        and int(size)
        > MAX_ALIGNMENT_FILE_BYTES
    ):
        raise MolecularAlignmentImportError(
            "The alignment file exceeds the 20 MiB upload limit."
        )

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    raw = uploaded_file.read(
        MAX_ALIGNMENT_FILE_BYTES + 1
    )

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    if not raw:
        raise MolecularAlignmentImportError(
            "The uploaded alignment file is empty."
        )

    if len(raw) > MAX_ALIGNMENT_FILE_BYTES:
        raise MolecularAlignmentImportError(
            "The alignment file exceeds the 20 MiB upload limit."
        )

    return filename, raw


def _resolve_source_format(
    filename: str,
) -> tuple[str, str, str]:
    suffix = Path(
        filename
    ).suffix.lower()

    if suffix in DEFERRED_EXTENSIONS:
        raise MolecularAlignmentImportError(
            (
                f"{suffix} alignment semantics are not yet supported. "
                "Use aligned FASTA (.afa/.fa/.fasta), "
                "CLUSTAL (.aln), or Stockholm (.sto/.stk)."
            )
        )

    format_info = SOURCE_FORMATS.get(
        suffix
    )

    if format_info is None:
        raise MolecularAlignmentImportError(
            (
                "Unsupported protein alignment format. "
                "Accepted extensions: "
                ".afa, .fa, .fasta, .aln, .sto, .stk."
            )
        )

    return format_info


def _decode_alignment(
    raw: bytes,
) -> str:
    try:
        return raw.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError as exc:
        raise MolecularAlignmentImportError(
            "Protein alignment files must be UTF-8 text."
        ) from exc


def _validate_render_sequence(
    sequence: str,
    *,
    row_name: str,
) -> str:
    normalized = str(
        sequence
    ).upper()

    invalid = sorted(
        set(
            normalized
        )
        - ALLOWED_RENDER_SYMBOLS
    )

    if invalid:
        raise MolecularAlignmentImportError(
            (
                f"Alignment row {row_name!r} contains "
                "unsupported symbols: "
                + " ".join(
                    invalid
                )
            )
        )

    return normalized


def parse_molecular_alignment(
    uploaded_file,
) -> dict:
    filename, raw = _read_uploaded_bytes(
        uploaded_file
    )

    (
        biopython_format,
        source_format,
        source_format_label,
    ) = _resolve_source_format(
        filename
    )

    text = _decode_alignment(
        raw
    )

    try:
        alignment = AlignIO.read(
            StringIO(
                text
            ),
            biopython_format,
        )
    except Exception as exc:
        raise MolecularAlignmentImportError(
            (
                f"Could not parse {source_format_label} alignment: "
                f"{exc}"
            )
        ) from exc

    sequence_count = len(
        alignment
    )

    if sequence_count < 2:
        raise MolecularAlignmentImportError(
            "A protein MSA must contain at least two aligned sequences."
        )

    if sequence_count > MAX_ALIGNMENT_SEQUENCES:
        raise MolecularAlignmentImportError(
            (
                "The alignment contains too many sequences "
                f"({sequence_count}; maximum "
                f"{MAX_ALIGNMENT_SEQUENCES})."
            )
        )

    alignment_length = (
        alignment.get_alignment_length()
    )

    if alignment_length < 1:
        raise MolecularAlignmentImportError(
            "The alignment has no columns."
        )

    if alignment_length > MAX_ALIGNMENT_COLUMNS:
        raise MolecularAlignmentImportError(
            (
                "The alignment contains too many columns "
                f"({alignment_length}; maximum "
                f"{MAX_ALIGNMENT_COLUMNS})."
            )
        )

    rows = []
    seen_names = set()

    for index, record in enumerate(
        alignment
    ):
        row_name = str(
            record.id
            or ""
        ).strip()

        if not row_name:
            raise MolecularAlignmentImportError(
                (
                    "Every alignment row must have "
                    "a source sequence identifier."
                )
            )

        if row_name in seen_names:
            raise MolecularAlignmentImportError(
                (
                    "Duplicate alignment identifier: "
                    f"{row_name!r}."
                )
            )

        seen_names.add(
            row_name
        )

        sequence = _validate_render_sequence(
            str(
                record.seq
            ),
            row_name=row_name,
        )

        if len(sequence) != alignment_length:
            raise MolecularAlignmentImportError(
                (
                    "The parsed alignment is not rectangular: "
                    f"row {row_name!r} has {len(sequence)} "
                    f"columns but expected {alignment_length}."
                )
            )

        rows.append(
            {
                "index": index,
                "name": row_name,
                "sequence": sequence,
            }
        )

    checksum_sha256 = hashlib.sha256(
        raw
    ).hexdigest()

    return {
        "original_filename": filename,
        "source_format": source_format,
        "source_format_label": source_format_label,
        "checksum_sha256": checksum_sha256,
        "sequence_count": sequence_count,
        "alignment_length": alignment_length,
        "rows": rows,
    }
