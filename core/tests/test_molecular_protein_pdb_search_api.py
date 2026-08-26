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
from core.services.rcsb_pdb import (
    RcsbPdbSearchError,
)


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
class MolecularProteinPdbSearchApiTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username="pdb-search-owner",
                password="test-password",
            )
        )

        self.other = (
            get_user_model()
            .objects.create_user(
                username="pdb-search-other",
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name="PDB search Protein",
                sequence_type="protein",
                topology="linear",
                sequence="M" * 40,
                owner=self.user,
            )
        )

        self.dna = (
            MolecularSequence.objects.create(
                name="PDB search DNA",
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
            "molecular_sequence_pdb_search_api",
            [
                (
                    molecule
                    or self.protein
                ).id,
            ],
        )

    @patch(
        "core.services.rcsb_pdb.search_pdb_by_sequence"
    )
    def test_search_returns_enriched_hits(
        self,
        search,
    ):
        search.return_value = {
            "query_length": 40,
            "identity_cutoff": 0.9,
            "evalue_cutoff": 0.1,
            "requested_rows": 10,
            "total_count": 1,
            "hits": [
                {
                    "identifier": "1ABC_1",
                    "pdb_id": "1ABC",
                    "entity_id": "1",
                    "identity": 1.0,
                    "query_coverage": 1.0,
                    "evalue": 0.0,
                    "experimental_method": "X-ray",
                    "resolution": 1.5,
                    "chains": [
                        "A",
                    ],
                }
            ],
        }

        response = self.client.get(
            self.url(),
            {
                "identity": "0.90",
                "evalue": "0.1",
                "rows": "10",
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

        self.assertEqual(
            payload[
                "record"
            ][
                "id"
            ],
            self.protein.id,
        )

        self.assertEqual(
            payload[
                "search"
            ][
                "hits"
            ][0][
                "pdb_id"
            ],
            "1ABC",
        )

        search.assert_called_once_with(
            self.protein.sequence,
            identity_cutoff=0.9,
            evalue_cutoff=0.1,
            rows=10,
        )

    def test_nonprotein_is_rejected(self):
        response = self.client.get(
            self.url(
                self.dna
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_post_is_rejected(self):
        response = self.client.post(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_invalid_parameters_are_rejected(self):
        response = self.client.get(
            self.url(),
            {
                "identity": "not-a-number",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch(
        "core.services.rcsb_pdb.search_pdb_by_sequence"
    )
    def test_upstream_failure_returns_502(
        self,
        search,
    ):
        search.side_effect = (
            RcsbPdbSearchError(
                "upstream unavailable"
            )
        )

        response = self.client.get(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            502,
        )

    def test_other_user_cannot_read_record(self):
        self.client.force_login(
            self.other
        )

        response = self.client.get(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            404,
        )
