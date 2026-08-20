from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    MolecularStructure,
)
from core.services.rcsb_pdb import (
    RcsbPdbQueryError,
    RcsbPdbSearchError,
)


MMCIF_CONTENT = (
    b"data_6TC2\n"
    b"#\n"
    b"loop_\n"
    b"_atom_site.group_PDB\n"
    b"_atom_site.id\n"
    b"_atom_site.type_symbol\n"
    b"_atom_site.label_atom_id\n"
    b"_atom_site.label_comp_id\n"
    b"_atom_site.label_asym_id\n"
    b"_atom_site.label_seq_id\n"
    b"_atom_site.Cartn_x\n"
    b"_atom_site.Cartn_y\n"
    b"_atom_site.Cartn_z\n"
    b"ATOM 1 C CA ALA A 1 1.0 2.0 3.0\n"
    b"#\n"
)


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    ).removeprefix(
        "/biobank"
    )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularProteinPdbPreviewApiTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username="pdb-preview-owner",
                password="test-password",
            )
        )

        self.other = (
            get_user_model()
            .objects.create_user(
                username="pdb-preview-other",
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name="PDB preview Protein",
                sequence_type="protein",
                topology="linear",
                sequence="M" * 40,
                owner=self.user,
            )
        )

        self.dna = (
            MolecularSequence.objects.create(
                name="PDB preview DNA",
                sequence_type="dna",
                topology="linear",
                sequence="ATGC" * 20,
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
            "molecular_sequence_pdb_preview_api",
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
    def test_preview_returns_inline_mmcif_without_persisting(
        self,
        fetch,
    ):
        fetch.return_value = {
            "pdb_id": "6TC2",
            "filename": "6TC2.cif",
            "content": MMCIF_CONTENT,
            "size_bytes": len(
                MMCIF_CONTENT
            ),
        }

        before = (
            MolecularStructure.objects.count()
        )

        response = self.client.get(
            self.url(),
            {
                "pdb_id": "6TC2",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.content,
            MMCIF_CONTENT,
        )

        self.assertEqual(
            response.headers[
                "Content-Type"
            ],
            "chemical/x-cif",
        )

        self.assertEqual(
            response.headers[
                "X-Biobank-PDB-Preview"
            ],
            "6TC2",
        )

        self.assertIn(
            'filename="6TC2.cif"',
            response.headers[
                "Content-Disposition"
            ],
        )

        self.assertEqual(
            MolecularStructure.objects.count(),
            before,
        )

        fetch.assert_called_once_with(
            "6TC2"
        )

    def test_post_is_rejected(self):
        response = self.client.post(
            self.url(),
            {
                "pdb_id": "6TC2",
            },
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    @patch(
        "core.services.rcsb_pdb.fetch_pdb_mmcif"
    )
    def test_invalid_pdb_id_returns_400(
        self,
        fetch,
    ):
        fetch.side_effect = (
            RcsbPdbQueryError(
                "Invalid four-character PDB identifier."
            )
        )

        response = self.client.get(
            self.url(),
            {
                "pdb_id": "INVALID",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch(
        "core.services.rcsb_pdb.fetch_pdb_mmcif"
    )
    def test_upstream_failure_returns_502(
        self,
        fetch,
    ):
        fetch.side_effect = (
            RcsbPdbSearchError(
                "upstream unavailable"
            )
        )

        response = self.client.get(
            self.url(),
            {
                "pdb_id": "6TC2",
            },
        )

        self.assertEqual(
            response.status_code,
            502,
        )

    def test_nonprotein_is_rejected(self):
        response = self.client.get(
            self.url(
                self.dna
            ),
            {
                "pdb_id": "6TC2",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_other_user_cannot_preview_owner_record(
        self,
    ):
        self.client.force_login(
            self.other
        )

        response = self.client.get(
            self.url(),
            {
                "pdb_id": "6TC2",
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )
