from __future__ import annotations

from collections import defaultdict
import io
import re

from Bio.Align import PairwiseAligner
from Bio.PDB import PDBParser
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio.PDB.Polypeptide import is_aa
from Bio.SeqUtils import seq1


class MolecularStructureMappingError(
    ValueError
):
    """Raised when a structure cannot be mapped safely."""


def normalize_protein_sequence(
    sequence,
):
    normalized = re.sub(
        r"\s+",
        "",
        str(
            sequence
            or ""
        ).upper(),
    )

    if not normalized:
        raise MolecularStructureMappingError(
            "A Protein sequence is required for structure mapping."
        )

    if not re.fullmatch(
        r"[A-Z]+",
        normalized,
    ):
        raise MolecularStructureMappingError(
            "The Protein sequence contains unsupported characters."
        )

    return normalized


def _clean_cif_value(
    value,
):
    text = str(
        value
        or ""
    ).strip()

    if text in {
        ".",
        "?",
    }:
        return ""

    return text


def _as_list(
    value,
):
    if value is None:
        return []

    if isinstance(
        value,
        list,
    ):
        return [
            str(
                item
            )
            for item in value
        ]

    return [
        str(
            value
        )
    ]


def _safe_int(
    value,
):
    value = _clean_cif_value(
        value
    )

    if not value:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _one_letter(
    residue_name,
):
    residue_name = str(
        residue_name
        or ""
    ).strip()

    if not residue_name:
        return "X"

    try:
        result = seq1(
            residue_name,
            undef_code="X",
        )

    except Exception:
        return "X"

    result = str(
        result
        or "X"
    ).upper()

    if len(
        result
    ) != 1:
        return "X"

    return result


def _align_sequences(
    registry_sequence,
    structure_sequence,
):
    registry_sequence = (
        normalize_protein_sequence(
            registry_sequence
        )
    )

    structure_sequence = (
        normalize_protein_sequence(
            structure_sequence
        )
    )

    aligner = PairwiseAligner(
        mode="global"
    )

    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -10
    aligner.extend_gap_score = -0.5

    alignments = aligner.align(
        registry_sequence,
        structure_sequence,
    )

    if len(
        alignments
    ) == 0:
        raise MolecularStructureMappingError(
            "No sequence alignment could be generated."
        )

    alignment = alignments[
        0
    ]

    coordinates = alignment.coordinates

    registry_coordinates = (
        coordinates[
            0
        ]
    )

    structure_coordinates = (
        coordinates[
            1
        ]
    )

    position_map = {}

    aligned_positions = 0
    identical_positions = 0

    for index in range(
        len(
            registry_coordinates
        )
        - 1
    ):
        registry_start = int(
            registry_coordinates[
                index
            ]
        )

        registry_end = int(
            registry_coordinates[
                index + 1
            ]
        )

        structure_start = int(
            structure_coordinates[
                index
            ]
        )

        structure_end = int(
            structure_coordinates[
                index + 1
            ]
        )

        registry_delta = (
            registry_end
            - registry_start
        )

        structure_delta = (
            structure_end
            - structure_start
        )

        if (
            registry_delta <= 0
            or structure_delta <= 0
        ):
            continue

        if (
            registry_delta
            != structure_delta
        ):
            raise MolecularStructureMappingError(
                (
                    "Unexpected non-collinear alignment block "
                    "while building the residue map."
                )
            )

        for offset in range(
            registry_delta
        ):
            registry_index = (
                registry_start
                + offset
            )

            structure_index = (
                structure_start
                + offset
            )

            registry_position = (
                registry_index
                + 1
            )

            structure_position = (
                structure_index
                + 1
            )

            registry_residue = (
                registry_sequence[
                    registry_index
                ]
            )

            structure_residue = (
                structure_sequence[
                    structure_index
                ]
            )

            identical = (
                registry_residue
                == structure_residue
            )

            position_map[
                registry_position
            ] = {
                "registry_position":
                    registry_position,

                "registry_residue":
                    registry_residue,

                "structure_position":
                    structure_position,

                "structure_residue":
                    structure_residue,

                "identical":
                    identical,
            }

            aligned_positions += 1

            if identical:
                identical_positions += 1

    identity = (
        identical_positions
        / aligned_positions
        if aligned_positions
        else 0.0
    )

    alignment_coverage = (
        aligned_positions
        / len(
            registry_sequence
        )
        if registry_sequence
        else 0.0
    )

    return {
        "registry_length":
            len(
                registry_sequence
            ),

        "structure_sequence_length":
            len(
                structure_sequence
            ),

        "aligned_positions":
            aligned_positions,

        "identical_positions":
            identical_positions,

        "identity":
            identity,

        "alignment_coverage":
            alignment_coverage,

        "score":
            float(
                alignment.score
            ),

        "position_map":
            position_map,
    }


def _entity_sequences_from_mmcif(
    data,
):
    entity_ids = _as_list(
        data.get(
            "_entity_poly_seq.entity_id"
        )
    )

    numbers = _as_list(
        data.get(
            "_entity_poly_seq.num"
        )
    )

    monomers = _as_list(
        data.get(
            "_entity_poly_seq.mon_id"
        )
    )

    positions = defaultdict(
        dict
    )

    for entity_id, number, monomer in zip(
        entity_ids,
        numbers,
        monomers,
    ):
        entity_id = _clean_cif_value(
            entity_id
        )

        position = _safe_int(
            number
        )

        if (
            not entity_id
            or position is None
            or position < 1
        ):
            continue

        positions[
            entity_id
        ][
            position
        ] = _one_letter(
            monomer
        )

    sequences = {}

    for entity_id, residues in positions.items():
        if not residues:
            continue

        maximum = max(
            residues
        )

        sequence = "".join(
            residues.get(
                position,
                "X",
            )
            for position in range(
                1,
                maximum + 1,
            )
        )

        sequences[
            entity_id
        ] = sequence

    return sequences


def _struct_asym_entities(
    data,
):
    asym_ids = _as_list(
        data.get(
            "_struct_asym.id"
        )
    )

    entity_ids = _as_list(
        data.get(
            "_struct_asym.entity_id"
        )
    )

    return {
        _clean_cif_value(
            asym_id
        ):
            _clean_cif_value(
                entity_id
            )

        for asym_id, entity_id in zip(
            asym_ids,
            entity_ids,
        )

        if (
            _clean_cif_value(
                asym_id
            )
            and _clean_cif_value(
                entity_id
            )
        )
    }


def _resolved_mmcif_residues(
    data,
):
    columns = {
        "group":
            _as_list(
                data.get(
                    "_atom_site.group_PDB"
                )
            ),

        "entity":
            _as_list(
                data.get(
                    "_atom_site.label_entity_id"
                )
            ),

        "label_asym":
            _as_list(
                data.get(
                    "_atom_site.label_asym_id"
                )
            ),

        "auth_asym":
            _as_list(
                data.get(
                    "_atom_site.auth_asym_id"
                )
            ),

        "label_seq":
            _as_list(
                data.get(
                    "_atom_site.label_seq_id"
                )
            ),

        "auth_seq":
            _as_list(
                data.get(
                    "_atom_site.auth_seq_id"
                )
            ),

        "label_comp":
            _as_list(
                data.get(
                    "_atom_site.label_comp_id"
                )
            ),

        "auth_comp":
            _as_list(
                data.get(
                    "_atom_site.auth_comp_id"
                )
            ),

        "ins_code":
            _as_list(
                data.get(
                    "_atom_site.pdbx_PDB_ins_code"
                )
            ),
    }

    row_count = max(
        (
            len(
                values
            )
            for values in columns.values()
        ),
        default=0,
    )

    def value(
        name,
        index,
    ):
        values = columns[
            name
        ]

        if index >= len(
            values
        ):
            return ""

        return _clean_cif_value(
            values[
                index
            ]
        )

    residues = defaultdict(
        dict
    )

    for index in range(
        row_count
    ):
        if value(
            "group",
            index,
        ) != "ATOM":
            continue

        label_asym = value(
            "label_asym",
            index,
        )

        entity_id = value(
            "entity",
            index,
        )

        label_seq_id = _safe_int(
            value(
                "label_seq",
                index,
            )
        )

        if (
            not label_asym
            or not entity_id
            or label_seq_id is None
        ):
            continue

        residue = {
            "entity_id":
                entity_id,

            "label_asym_id":
                label_asym,

            "auth_asym_id":
                value(
                    "auth_asym",
                    index,
                ),

            "label_seq_id":
                label_seq_id,

            "auth_seq_id":
                _safe_int(
                    value(
                        "auth_seq",
                        index,
                    )
                ),

            "insertion_code":
                value(
                    "ins_code",
                    index,
                ),

            "label_comp_id":
                value(
                    "label_comp",
                    index,
                ),

            "auth_comp_id":
                value(
                    "auth_comp",
                    index,
                ),
        }

        residues[
            label_asym
        ][
            label_seq_id
        ] = residue

    return residues


def _build_mmcif_candidates(
    registry_sequence,
    data,
    *,
    entity_id=None,
):
    registry_sequence = (
        normalize_protein_sequence(
            registry_sequence
        )
    )

    entity_sequences = (
        _entity_sequences_from_mmcif(
            data
        )
    )

    asym_entities = (
        _struct_asym_entities(
            data
        )
    )

    resolved_by_asym = (
        _resolved_mmcif_residues(
            data
        )
    )

    requested_entity = (
        str(
            entity_id
        ).strip()
        if entity_id is not None
        else ""
    )

    candidates = []

    for label_asym_id, current_entity_id in (
        asym_entities.items()
    ):
        if (
            requested_entity
            and current_entity_id
                != requested_entity
        ):
            continue

        structure_sequence = (
            entity_sequences.get(
                current_entity_id
            )
        )

        if not structure_sequence:
            continue

        alignment = _align_sequences(
            registry_sequence,
            structure_sequence,
        )

        resolved = (
            resolved_by_asym.get(
                label_asym_id,
                {}
            )
        )

        auth_asym_ids = sorted(
            {
                str(
                    residue.get(
                        "auth_asym_id"
                    )
                    or ""
                )
                for residue in resolved.values()
                if residue.get(
                    "auth_asym_id"
                )
            }
        )

        mapping = []

        resolved_registry_positions = []

        for registry_position in sorted(
            alignment[
                "position_map"
            ]
        ):
            base = dict(
                alignment[
                    "position_map"
                ][
                    registry_position
                ]
            )

            structure_position = (
                base[
                    "structure_position"
                ]
            )

            coordinate = resolved.get(
                structure_position
            )

            entry = {
                **base,

                "resolved":
                    coordinate
                    is not None,

                "entity_id":
                    current_entity_id,

                "label_asym_id":
                    label_asym_id,

                "auth_asym_id":
                    (
                        coordinate.get(
                            "auth_asym_id"
                        )
                        if coordinate
                        else (
                            auth_asym_ids[
                                0
                            ]
                            if auth_asym_ids
                            else ""
                        )
                    ),

                "label_seq_id":
                    structure_position,

                "auth_seq_id":
                    (
                        coordinate.get(
                            "auth_seq_id"
                        )
                        if coordinate
                        else None
                    ),

                "insertion_code":
                    (
                        coordinate.get(
                            "insertion_code"
                        )
                        if coordinate
                        else ""
                    ),
            }

            if coordinate:
                resolved_registry_positions.append(
                    registry_position
                )

            mapping.append(
                entry
            )

        resolved_count = len(
            resolved_registry_positions
        )

        resolved_coverage = (
            resolved_count
            / len(
                registry_sequence
            )
        )

        candidates.append(
            {
                "candidate_id":
                    (
                        "mmcif:"
                        f"{current_entity_id}:"
                        f"{label_asym_id}"
                    ),

                "source_format":
                    "mmcif",

                "mapping_basis":
                    (
                        "entity_sequence_with_"
                        "resolved_coordinate_mask"
                    ),

                "entity_id":
                    current_entity_id,

                "label_asym_id":
                    label_asym_id,

                "auth_asym_id":
                    (
                        auth_asym_ids[
                            0
                        ]
                        if auth_asym_ids
                        else ""
                    ),

                "auth_asym_ids":
                    auth_asym_ids,

                "registry_length":
                    alignment[
                        "registry_length"
                    ],

                "structure_sequence_length":
                    alignment[
                        "structure_sequence_length"
                    ],

                "aligned_positions":
                    alignment[
                        "aligned_positions"
                    ],

                "identical_positions":
                    alignment[
                        "identical_positions"
                    ],

                "identity":
                    alignment[
                        "identity"
                    ],

                "alignment_coverage":
                    alignment[
                        "alignment_coverage"
                    ],

                "alignment_score":
                    alignment[
                        "score"
                    ],

                "resolved_mapped_positions":
                    resolved_count,

                "resolved_coverage":
                    resolved_coverage,

                "resolved_registry_positions":
                    resolved_registry_positions,

                "mapping":
                    mapping,
            }
        )

    return candidates


def _build_pdb_candidates(
    registry_sequence,
    text,
):
    registry_sequence = (
        normalize_protein_sequence(
            registry_sequence
        )
    )

    parser = PDBParser(
        QUIET=True
    )

    try:
        structure = parser.get_structure(
            "uploaded_structure",
            io.StringIO(
                text
            ),
        )

    except Exception as exc:
        raise MolecularStructureMappingError(
            (
                "The uploaded PDB file could not "
                f"be parsed: {exc}"
            )
        ) from exc

    try:
        model = next(
            structure.get_models()
        )

    except StopIteration as exc:
        raise MolecularStructureMappingError(
            "The PDB file does not contain a structural model."
        ) from exc

    candidates = []

    for chain in model:
        residues = []

        for residue in chain:
            if not is_aa(
                residue,
                standard=False,
            ):
                continue

            amino_acid = _one_letter(
                residue.get_resname()
            )

            residue_id = residue.id

            auth_seq_id = (
                int(
                    residue_id[
                        1
                    ]
                )
            )

            insertion_code = str(
                residue_id[
                    2
                ]
                or ""
            ).strip()

            residues.append(
                {
                    "structure_residue":
                        amino_acid,

                    "auth_seq_id":
                        auth_seq_id,

                    "insertion_code":
                        insertion_code,
                }
            )

        if not residues:
            continue

        structure_sequence = "".join(
            residue[
                "structure_residue"
            ]
            for residue in residues
        )

        alignment = _align_sequences(
            registry_sequence,
            structure_sequence,
        )

        mapping = []

        resolved_registry_positions = []

        for registry_position in sorted(
            alignment[
                "position_map"
            ]
        ):
            base = dict(
                alignment[
                    "position_map"
                ][
                    registry_position
                ]
            )

            coordinate_index = (
                base[
                    "structure_position"
                ]
                - 1
            )

            coordinate = (
                residues[
                    coordinate_index
                ]
            )

            resolved_registry_positions.append(
                registry_position
            )

            mapping.append(
                {
                    **base,

                    "resolved":
                        True,

                    "entity_id":
                        "",

                    "label_asym_id":
                        "",

                    "auth_asym_id":
                        str(
                            chain.id
                        ),

                    "label_seq_id":
                        None,

                    "auth_seq_id":
                        coordinate[
                            "auth_seq_id"
                        ],

                    "insertion_code":
                        coordinate[
                            "insertion_code"
                        ],
                }
            )

        resolved_count = len(
            resolved_registry_positions
        )

        candidates.append(
            {
                "candidate_id":
                    (
                        "pdb:"
                        f"{chain.id}"
                    ),

                "source_format":
                    "pdb",

                "mapping_basis":
                    "resolved_coordinate_sequence",

                "entity_id":
                    "",

                "label_asym_id":
                    "",

                "auth_asym_id":
                    str(
                        chain.id
                    ),

                "auth_asym_ids": [
                    str(
                        chain.id
                    ),
                ],

                "registry_length":
                    alignment[
                        "registry_length"
                    ],

                "structure_sequence_length":
                    alignment[
                        "structure_sequence_length"
                    ],

                "aligned_positions":
                    alignment[
                        "aligned_positions"
                    ],

                "identical_positions":
                    alignment[
                        "identical_positions"
                    ],

                "identity":
                    alignment[
                        "identity"
                    ],

                "alignment_coverage":
                    alignment[
                        "alignment_coverage"
                    ],

                "alignment_score":
                    alignment[
                        "score"
                    ],

                "resolved_mapped_positions":
                    resolved_count,

                "resolved_coverage":
                    (
                        resolved_count
                        / len(
                            registry_sequence
                        )
                    ),

                "resolved_registry_positions":
                    resolved_registry_positions,

                "mapping":
                    mapping,
            }
        )

    return candidates


def rank_structure_mapping_candidates(
    candidates,
):
    return sorted(
        candidates,
        key=lambda candidate: (
            float(
                candidate.get(
                    "identity"
                )
                or 0
            ),

            float(
                candidate.get(
                    "alignment_coverage"
                )
                or 0
            ),

            float(
                candidate.get(
                    "resolved_coverage"
                )
                or 0
            ),

            int(
                candidate.get(
                    "resolved_mapped_positions"
                )
                or 0
            ),
        ),
        reverse=True,
    )


def build_structure_residue_mapping(
    registry_sequence,
    content,
    *,
    source_format,
    entity_id=None,
):
    registry_sequence = (
        normalize_protein_sequence(
            registry_sequence
        )
    )

    if isinstance(
        content,
        bytes,
    ):
        text = content.decode(
            "utf-8",
            errors="replace",
        )
    else:
        text = str(
            content
            or ""
        )

    if not text.strip():
        raise MolecularStructureMappingError(
            "The structure content is empty."
        )

    source_format = str(
        source_format
        or ""
    ).strip().lower()

    if source_format == "mmcif":
        try:
            data = MMCIF2Dict(
                io.StringIO(
                    text
                )
            )

        except Exception as exc:
            raise MolecularStructureMappingError(
                (
                    "The mmCIF file could not "
                    f"be parsed: {exc}"
                )
            ) from exc

        candidates = _build_mmcif_candidates(
            registry_sequence,
            data,
            entity_id=entity_id,
        )

    elif source_format == "pdb":
        candidates = _build_pdb_candidates(
            registry_sequence,
            text,
        )

    else:
        raise MolecularStructureMappingError(
            (
                "Unsupported mapping format. "
                "Expected pdb or mmcif."
            )
        )

    candidates = rank_structure_mapping_candidates(
        candidates
    )

    return {
        "registry_length":
            len(
                registry_sequence
            ),

        "source_format":
            source_format,

        "requested_entity_id":
            (
                str(
                    entity_id
                )
                if entity_id is not None
                else ""
            ),

        "candidate_count":
            len(
                candidates
            ),

        "candidates":
            candidates,
    }


def resolved_entries_for_registry_range(
    candidate,
    start,
    end,
):
    try:
        start = int(
            start
        )

        end = int(
            end
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise MolecularStructureMappingError(
            "Invalid Registry residue range."
        ) from exc

    if start > end:
        start, end = (
            end,
            start,
        )

    return [
        entry
        for entry in (
            candidate.get(
                "mapping"
            )
            or []
        )
        if (
            entry.get(
                "resolved"
            )
            and start
                <= int(
                    entry[
                        "registry_position"
                    ]
                )
                <= end
        )
    ]
