from __future__ import annotations

import hashlib
from pathlib import Path


class MolecularStructureImportError(
    ValueError
):
    """Raised when a tertiary-structure upload is invalid."""


_HEAD_LIMIT = 4 * 1024 * 1024


def _source_format_from_filename(
    filename,
):
    suffix = Path(
        filename
    ).suffix.lower()

    if suffix == ".pdb":
        return "pdb"

    if suffix in {
        ".cif",
        ".mmcif",
    }:
        return "mmcif"

    raise MolecularStructureImportError(
        (
            "Unsupported structure format. "
            "Upload a .pdb, .cif, or .mmcif file."
        )
    )


def _validate_pdb_head(
    text,
):
    has_coordinates = any(
        line.startswith(
            (
                "ATOM  ",
                "HETATM",
            )
        )
        for line in text.splitlines()
    )

    if not has_coordinates:
        raise MolecularStructureImportError(
            (
                "The PDB file does not contain "
                "ATOM or HETATM coordinate records."
            )
        )


def _validate_mmcif_head(
    text,
):
    normalized = text.lstrip()

    if not normalized.startswith(
        "data_"
    ):
        raise MolecularStructureImportError(
            (
                "The mmCIF file does not begin "
                "with a data_ block."
            )
        )

    if "_atom_site." not in text:
        raise MolecularStructureImportError(
            (
                "The mmCIF file does not contain "
                "an _atom_site coordinate table."
            )
        )


def parse_molecular_structure(
    uploaded_file,
):
    if uploaded_file is None:
        raise MolecularStructureImportError(
            "A structure file is required."
        )

    original_filename = Path(
        str(
            getattr(
                uploaded_file,
                "name",
                "",
            )
            or ""
        )
    ).name

    if not original_filename:
        raise MolecularStructureImportError(
            "The structure file requires a filename."
        )

    source_format = (
        _source_format_from_filename(
            original_filename
        )
    )

    hasher = hashlib.sha256()
    head = bytearray()
    size_bytes = 0

    try:
        chunks = uploaded_file.chunks()
    except AttributeError:
        chunks = iter(
            lambda: uploaded_file.read(
                1024 * 1024
            ),
            b"",
        )

    for chunk in chunks:
        if not chunk:
            continue

        if isinstance(
            chunk,
            str,
        ):
            chunk = chunk.encode(
                "utf-8"
            )

        hasher.update(
            chunk
        )

        size_bytes += len(
            chunk
        )

        if len(head) < _HEAD_LIMIT:
            remaining = (
                _HEAD_LIMIT
                - len(head)
            )

            head.extend(
                chunk[:remaining]
            )

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    if size_bytes == 0:
        raise MolecularStructureImportError(
            "The structure file is empty."
        )

    head_text = bytes(
        head
    ).decode(
        "utf-8",
        errors="replace",
    )

    if source_format == "pdb":
        _validate_pdb_head(
            head_text
        )
    else:
        _validate_mmcif_head(
            head_text
        )

    return {
        "original_filename": (
            original_filename
        ),
        "source_format": (
            source_format
        ),
        "checksum_sha256": (
            hasher.hexdigest()
        ),
        "size_bytes": (
            size_bytes
        ),
    }
