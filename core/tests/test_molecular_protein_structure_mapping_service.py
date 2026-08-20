from django.test import SimpleTestCase

from core.services.molecular_structure_mapping import (
    build_structure_residue_mapping,
    resolved_entries_for_registry_range,
)


MMCIF = b"""data_mapping_test
#
loop_
_entity_poly_seq.entity_id
_entity_poly_seq.num
_entity_poly_seq.mon_id
2 1 ALA
2 2 CYS
2 3 ASP
2 4 GLU
2 5 PHE
2 6 GLY
#
loop_
_struct_asym.id
_struct_asym.entity_id
C 2
D 2
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.label_entity_id
_atom_site.label_asym_id
_atom_site.auth_asym_id
_atom_site.label_seq_id
_atom_site.auth_seq_id
_atom_site.label_comp_id
_atom_site.auth_comp_id
_atom_site.pdbx_PDB_ins_code
ATOM 1 2 C a 1 10 ALA ALA ?
ATOM 2 2 C a 2 11 CYS CYS ?
ATOM 3 2 C a 5 14 PHE PHE ?
ATOM 4 2 C a 6 15 GLY GLY ?
ATOM 5 2 D b 5 1 PHE PHE ?
ATOM 6 2 D b 6 2 GLY GLY ?
#
"""


PDB = """\
ATOM      1  CA  ALA A  10       0.000   0.000   0.000  1.00 20.00           C
ATOM      2  CA  CYS A  11       1.000   0.000   0.000  1.00 20.00           C
ATOM      3  CA  ASP A  12       2.000   0.000   0.000  1.00 20.00           C
ATOM      4  CA  GLU A  13       3.000   0.000   0.000  1.00 20.00           C
ATOM      5  CA  PHE A  14       4.000   0.000   0.000  1.00 20.00           C
ATOM      6  CA  GLY A  15       5.000   0.000   0.000  1.00 20.00           C
TER
END
"""


class MolecularStructureMappingServiceTests(
    SimpleTestCase
):
    def test_mmcif_maps_registry_to_label_sequence(
        self,
    ):
        result = (
            build_structure_residue_mapping(
                "ACDEFG",
                MMCIF,
                source_format="mmcif",
                entity_id="2",
            )
        )

        self.assertEqual(
            result[
                "candidate_count"
            ],
            2,
        )

        best = result[
            "candidates"
        ][0]

        self.assertEqual(
            best[
                "label_asym_id"
            ],
            "C",
        )

        self.assertEqual(
            best[
                "auth_asym_id"
            ],
            "a",
        )

        self.assertEqual(
            best[
                "identity"
            ],
            1.0,
        )

        self.assertEqual(
            best[
                "alignment_coverage"
            ],
            1.0,
        )

        self.assertEqual(
            best[
                "resolved_registry_positions"
            ],
            [
                1,
                2,
                5,
                6,
            ],
        )

        mapping = {
            item[
                "registry_position"
            ]:
                item
            for item in best[
                "mapping"
            ]
        }

        self.assertTrue(
            mapping[
                1
            ][
                "resolved"
            ]
        )

        self.assertEqual(
            mapping[
                1
            ][
                "label_seq_id"
            ],
            1,
        )

        self.assertEqual(
            mapping[
                1
            ][
                "auth_seq_id"
            ],
            10,
        )

        self.assertFalse(
            mapping[
                3
            ][
                "resolved"
            ]
        )

        self.assertEqual(
            mapping[
                3
            ][
                "label_seq_id"
            ],
            3,
        )

        self.assertIsNone(
            mapping[
                3
            ][
                "auth_seq_id"
            ]
        )

    def test_resolved_range_omits_missing_coordinates(
        self,
    ):
        result = (
            build_structure_residue_mapping(
                "ACDEFG",
                MMCIF,
                source_format="mmcif",
                entity_id="2",
            )
        )

        best = result[
            "candidates"
        ][0]

        entries = (
            resolved_entries_for_registry_range(
                best,
                2,
                5,
            )
        )

        self.assertEqual(
            [
                item[
                    "registry_position"
                ]
                for item in entries
            ],
            [
                2,
                5,
            ],
        )

    def test_pdb_upload_maps_to_author_numbering(
        self,
    ):
        result = (
            build_structure_residue_mapping(
                "ACDEFG",
                PDB,
                source_format="pdb",
            )
        )

        self.assertEqual(
            result[
                "candidate_count"
            ],
            1,
        )

        candidate = result[
            "candidates"
        ][0]

        self.assertEqual(
            candidate[
                "auth_asym_id"
            ],
            "A",
        )

        self.assertEqual(
            candidate[
                "identity"
            ],
            1.0,
        )

        self.assertEqual(
            candidate[
                "resolved_coverage"
            ],
            1.0,
        )

        mapping = candidate[
            "mapping"
        ]

        self.assertEqual(
            mapping[
                0
            ][
                "registry_position"
            ],
            1,
        )

        self.assertEqual(
            mapping[
                0
            ][
                "auth_seq_id"
            ],
            10,
        )

        self.assertEqual(
            mapping[
                -1
            ][
                "registry_position"
            ],
            6,
        )

        self.assertEqual(
            mapping[
                -1
            ][
                "auth_seq_id"
            ],
            15,
        )
