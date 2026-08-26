from unittest.mock import (
    Mock,
    patch,
)

from django.contrib.auth import (
    get_user_model,
)

from django.test import (
    TestCase,
    override_settings,
)

from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
)

from core.services.structure_search import (
    StructureSearchQueryError,
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
class MolecularStructureSearchApiTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username=(
                    "structure-search-owner"
                ),
                password="test-password",
            )
        )

        self.other = (
            get_user_model()
            .objects.create_user(
                username=(
                    "structure-search-other"
                ),
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name="Unified structure Protein",
                sequence_type="protein",
                topology="linear",
                sequence="M" * 40,
                owner=self.user,
            )
        )

        self.dna = (
            MolecularSequence.objects.create(
                name="Unified structure DNA",
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
            (
                "molecular_sequence_"
                "structure_search_api"
            ),
            [
                (
                    molecule
                    or self.protein
                ).id,
            ],
        )

    @staticmethod
    def result(
        payload,
    ):
        result = Mock()

        result.to_dict.return_value = (
            payload
        )

        return result

    def test_canonical_route(
        self,
    ):
        self.assertEqual(
            self.url(),
            (
                "/internal/lab-tools/"
                "molecular-registry/api/"
                f"records/{self.protein.id}/"
                "structure-search/"
            ),
        )

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_search_returns_experimental_and_predicted_hits(
        self,
        search,
    ):
        search.return_value = self.result(
            {
                "query_length": 40,
                "returned_count": 2,
                "hits": [
                    {
                        "provider": "rcsb",
                        "provider_name": (
                            "RCSB PDB"
                        ),
                        "source_type": (
                            "experimental"
                        ),
                        "accession": "6B3Q",
                        "canonical_key": (
                            "pdb:6B3Q:2"
                        ),
                        "entity_id": "2",
                        "identity": 1.0,
                        "sequence_coverage": 1.0,
                    },
                    {
                        "provider": (
                            "alphafold-db"
                        ),
                        "provider_name": (
                            "AlphaFold DB"
                        ),
                        "discovery_provider": (
                            "beacons3d"
                        ),
                        "source_type": (
                            "computational"
                        ),
                        "accession": (
                            "AF-P01308-F1"
                        ),
                        "canonical_key": (
                            "alphafold:"
                            "AF-P01308-F1"
                        ),
                        "confidence_type": (
                            "pLDDT"
                        ),
                        "confidence_value": 52.91,
                    },
                ],
                "providers": [
                    {
                        "provider": "rcsb",
                        "state": "available",
                    },
                    {
                        "provider": (
                            "beacons3d-exact"
                        ),
                        "state": "available",
                    },
                ],
            }
        )

        response = self.client.get(
            self.url(),
            {
                "rows": "7",
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
                "record"
            ][
                "sequence_length"
            ],
            40,
        )

        self.assertEqual(
            payload[
                "search"
            ][
                "returned_count"
            ],
            2,
        )

        self.assertEqual(
            payload[
                "search"
            ][
                "hits"
            ][0][
                "source_type"
            ],
            "experimental",
        )

        self.assertEqual(
            payload[
                "search"
            ][
                "hits"
            ][1][
                "provider"
            ],
            "alphafold-db",
        )

        search.assert_called_once_with(
            self.protein.sequence,
            rows=7,
        )

        search.return_value.to_dict.assert_called_once_with()

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_default_rows_is_ten(
        self,
        search,
    ):
        search.return_value = self.result(
            {
                "query_length": 40,
                "returned_count": 0,
                "hits": [],
                "providers": [],
            }
        )

        response = self.client.get(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        search.assert_called_once_with(
            self.protein.sequence,
            rows=10,
        )

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_provider_degradation_remains_http_200(
        self,
        search,
    ):
        search.return_value = self.result(
            {
                "query_length": 40,
                "returned_count": 1,
                "hits": [
                    {
                        "provider": (
                            "alphafold-db"
                        ),
                        "source_type": (
                            "computational"
                        ),
                        "accession": (
                            "AF-P01308-F1"
                        ),
                    },
                ],
                "providers": [
                    {
                        "provider": "rcsb",
                        "state": "degraded",
                        "message": (
                            "RCSB unavailable"
                        ),
                    },
                    {
                        "provider": (
                            "beacons3d-exact"
                        ),
                        "state": "available",
                    },
                ],
            }
        )

        response = self.client.get(
            self.url()
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
                "search"
            ][
                "providers"
            ][0][
                "state"
            ],
            "degraded",
        )

        self.assertEqual(
            payload[
                "search"
            ][
                "hits"
            ][0][
                "provider"
            ],
            "alphafold-db",
        )

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_invalid_rows_syntax_is_rejected(
        self,
        search,
    ):
        response = self.client.get(
            self.url(),
            {
                "rows": (
                    "not-a-number"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.json()[
                "message"
            ],
            (
                "Invalid structure "
                "search parameters."
            ),
        )

        search.assert_not_called()

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_service_query_error_is_http_400(
        self,
        search,
    ):
        search.side_effect = (
            StructureSearchQueryError(
                "Invalid rows."
            )
        )

        response = self.client.get(
            self.url(),
            {
                "rows": "0",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.json()[
                "message"
            ],
            "Invalid rows.",
        )

        search.assert_called_once_with(
            self.protein.sequence,
            rows=0,
        )

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_nonprotein_is_rejected(
        self,
        search,
    ):
        response = self.client.get(
            self.url(
                self.dna
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            response.json()[
                "message"
            ],
            (
                "Structure search is currently "
                "available only for Protein records."
            ),
        )

        search.assert_not_called()

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_post_is_rejected(
        self,
        search,
    ):
        response = self.client.post(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        self.assertEqual(
            response.json()[
                "message"
            ],
            "GET is required.",
        )

        search.assert_not_called()

    @patch(
        "core.services.structure_search."
        "search_structures_by_sequence"
    )
    def test_other_user_cannot_read_record(
        self,
        search,
    ):
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

        search.assert_not_called()

    def test_authentication_is_required(
        self,
    ):
        self.client.logout()

        response = self.client.get(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            302,
        )
