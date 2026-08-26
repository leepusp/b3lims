from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
)


MMCIF = b"""data_mapping_api
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
#
"""


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularProteinStructureMappingApiTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username="mapping-owner",
                password="test-password",
            )
        )

        self.other = (
            get_user_model()
            .objects.create_user(
                username="mapping-other",
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name="Mapping Protein",
                sequence_type="protein",
                topology="linear",
                sequence="ACDEFG",
                owner=self.user,
            )
        )

        self.dna = (
            MolecularSequence.objects.create(
                name="Mapping DNA",
                sequence_type="dna",
                topology="linear",
                sequence="ATGCATGC",
                owner=self.user,
            )
        )

        self.client.force_login(
            self.user
        )

    def url(
        self,
        molecule=None,
    ):
        return request_path(
            "molecular_sequence_pdb_mapping_api",
            [
                (
                    molecule
                    or self.protein
                ).id,
            ],
        )

    @patch(
        "core.services.rcsb_pdb.fetch_pdb_mmcif"
    )
    def test_mapping_returns_ranked_chain_candidates(
        self,
        fetch,
    ):
        fetch.return_value = {
            "pdb_id": "6B3Q",
            "filename": "6B3Q.cif",
            "content": MMCIF,
            "size_bytes": len(
                MMCIF
            ),
        }

        response = self.client.get(
            self.url(),
            {
                "pdb_id": "6B3Q",
                "entity_id": "2",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload[
                "status"
            ],
            "ok",
        )

        candidates = payload[
            "mapping"
        ][
            "candidates"
        ]

        self.assertEqual(
            len(
                candidates
            ),
            1,
        )

        candidate = candidates[
            0
        ]

        self.assertEqual(
            candidate[
                "label_asym_id"
            ],
            "C",
        )

        self.assertEqual(
            candidate[
                "identity"
            ],
            1.0,
        )

        self.assertEqual(
            candidate[
                "resolved_registry_positions"
            ],
            [
                1,
                2,
                5,
                6,
            ],
        )

    def test_post_is_rejected(self):
        response = self.client.post(
            self.url(),
            {
                "pdb_id": "6B3Q",
            },
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_nonprotein_is_rejected(self):
        response = self.client.get(
            self.url(
                self.dna
            ),
            {
                "pdb_id": "6B3Q",
                "entity_id": "2",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_other_user_cannot_read_mapping(
        self,
    ):
        self.client.force_login(
            self.other
        )

        response = self.client.get(
            self.url(),
            {
                "pdb_id": "6B3Q",
                "entity_id": "2",
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )
