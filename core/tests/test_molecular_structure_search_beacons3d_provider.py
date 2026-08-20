from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from core.services.structure_search.base import (
    StructureProviderError,
    StructureSearchQueryError,
)
from core.services.structure_search.models import (
    StructureEntity,
    StructureHit,
)
from core.services.structure_search.providers import (
    beacons3d,
)
from core.services.structure_search.search import (
    DEFAULT_PROVIDERS,
)


QUERY = (
    "MALWMRLLPLLALLALWGPDPAAA"
    "FVNQHLCGSHLVEALYLVCGERG"
    "FFYTPKTRREAEDLQVGQVELGG"
    "GPGAGSLQPLALEGSLQKRGIVE"
    "QCCTSICSLYQLENYCN"
)


def completed_payload():
    return [
        {
            "accession": "P01308",
            "id": "INS_HUMAN",
            "title": "Insulin",
            "description": (
                "Insulin OS=Homo sapiens "
                "OX=9606 GN=INS"
            ),
            "hit_length": 110,
            "hit_hsps": [
                {
                    "hsp_align_len": 110,
                    "hsp_bit_score": 231.5,
                    "hsp_identity": 100.0,
                }
            ],
            "summary": {
                "structures": [
                    {
                        "summary": {
                            "model_identifier": "6b3q",
                            "provider": "PDBe",
                            "model_category": (
                                "EXPERIMENTALLY "
                                "DETERMINED"
                            ),
                            "model_type": None,
                            "model_format": "MMCIF",
                            "model_url": (
                                "https://www.ebi.ac.uk/"
                                "pdbe/static/entry/"
                                "6b3q_updated.cif"
                            ),
                            "model_page_url": (
                                "https://www.ebi.ac.uk/"
                                "pdbe/entry/pdb/6b3q"
                            ),
                            "sequence_identity": 100.0,
                            "coverage": 1.0,
                            "uniprot_start": 1,
                            "uniprot_end": 110,
                            "experimental_method": (
                                "ELECTRON MICROSCOPY"
                            ),
                            "resolution": 3.7,
                            "confidence_type": None,
                            "confidence_avg_local_score": (
                                None
                            ),
                            "confidence_version": None,
                            "entities": [
                                {
                                    "entity_type": "POLYMER",
                                    "description": (
                                        "Insulin"
                                    ),
                                    "chain_ids": [
                                        "a",
                                        "b",
                                    ],
                                    "identifier": "P01308",
                                    "identifier_category": (
                                        "UNIPROT"
                                    ),
                                    "entity_poly_type": (
                                        "POLYPEPTIDE(L)"
                                    ),
                                },
                                {
                                    "entity_type": "POLYMER",
                                    "description": (
                                        "Insulin-degrading "
                                        "enzyme"
                                    ),
                                    "chain_ids": [
                                        "A",
                                        "B",
                                    ],
                                    "identifier": "P14735",
                                    "identifier_category": (
                                        "UNIPROT"
                                    ),
                                    "entity_poly_type": (
                                        "POLYPEPTIDE(L)"
                                    ),
                                },
                            ],
                        }
                    },
                    {
                        "summary": {
                            "model_identifier": (
                                "AF-P01308-F1"
                            ),
                            "provider": (
                                "AlphaFold DB"
                            ),
                            "model_category": (
                                "AB-INITIO"
                            ),
                            "model_type": "ATOMIC",
                            "model_format": "MMCIF",
                            "model_url": (
                                "https://alphafold.ebi."
                                "ac.uk/files/"
                                "AF-P01308-F1-"
                                "model_v6.cif"
                            ),
                            "model_page_url": (
                                "https://alphafold.ebi."
                                "ac.uk/entry/"
                                "AF-P01308-F1"
                            ),
                            "sequence_identity": 1.0,
                            "coverage": 1.0,
                            "uniprot_start": 1,
                            "uniprot_end": 110,
                            "experimental_method": None,
                            "resolution": None,
                            "confidence_type": "pLDDT",
                            "confidence_avg_local_score": (
                                52.91
                            ),
                            "confidence_version": None,
                            "entities": [
                                {
                                    "entity_type": "POLYMER",
                                    "description": "Insulin",
                                    "chain_ids": [
                                        "A",
                                    ],
                                    "identifier": "P01308",
                                    "identifier_category": (
                                        "UNIPROT"
                                    ),
                                    "entity_poly_type": (
                                        "POLYPEPTIDE(L)"
                                    ),
                                }
                            ],
                        }
                    },
                    {
                        "summary": {
                            "model_identifier": (
                                "P01308_25-110:"
                                "2lwz.1.A"
                            ),
                            "provider": "SWISS-MODEL",
                            "model_category": (
                                "TEMPLATE-BASED"
                            ),
                            "model_type": "ATOMIC",
                            "model_format": "MMCIF",
                            "model_url": (
                                "https://swissmodel."
                                "example/model.cif"
                            ),
                            "model_page_url": (
                                "https://swissmodel."
                                "example/model"
                            ),
                            "sequence_identity": 1.0,
                            "coverage": 0.782,
                            "uniprot_start": 25,
                            "uniprot_end": 110,
                            "experimental_method": None,
                            "resolution": None,
                            "confidence_type": (
                                "QMEANDisCo"
                            ),
                            "confidence_avg_local_score": (
                                0.523
                            ),
                            "confidence_version": "v1",
                            "entities": [
                                {
                                    "entity_type": "POLYMER",
                                    "description": (
                                        "Insulin model"
                                    ),
                                    "chain_ids": [
                                        "A",
                                    ],
                                    "identifier": "P01308",
                                    "identifier_category": (
                                        "UNIPROT"
                                    ),
                                    "entity_poly_type": (
                                        "POLYPEPTIDE(L)"
                                    ),
                                }
                            ],
                        }
                    },
                ]
            },
        }
    ]


class StructureSearchExtendedModelTests(
    SimpleTestCase
):
    def test_structure_entity_serializes_chain_ids(
        self,
    ):
        entity = StructureEntity(
            entity_type="POLYMER",
            chain_ids=(
                "A",
                "B",
            ),
            identifier="P01308",
            identifier_category="UNIPROT",
        )

        payload = entity.to_dict()

        self.assertEqual(
            payload[
                "chain_ids"
            ],
            [
                "A",
                "B",
            ],
        )

    def test_structure_hit_preserves_native_confidence(
        self,
    ):
        hit = StructureHit(
            provider="alphafold-db",
            provider_name="AlphaFold DB",
            discovery_provider="beacons3d",
            source_type="computational",
            model_type="ab-initio",
            accession="AF-P01308-F1",
            canonical_key=(
                "alphafold:AF-P01308-F1"
            ),
            confidence_type="pLDDT",
            confidence_value=52.91,
        )

        payload = hit.to_dict()

        self.assertEqual(
            payload[
                "confidence_type"
            ],
            "pLDDT",
        )

        self.assertEqual(
            payload[
                "confidence_value"
            ],
            52.91,
        )


class ThreeDBeaconsNormalizationTests(
    SimpleTestCase
):
    def test_pdb_model_does_not_invent_rcsb_entity_id(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        pdb = batch.hits[
            0
        ]

        self.assertEqual(
            pdb.provider,
            "pdbe",
        )

        self.assertEqual(
            pdb.discovery_provider,
            "beacons3d",
        )

        self.assertEqual(
            pdb.source_type,
            "experimental",
        )

        self.assertEqual(
            pdb.model_type,
            "experimental",
        )

        self.assertEqual(
            pdb.accession,
            "6b3q",
        )

        self.assertEqual(
            pdb.entity_id,
            "",
        )

        self.assertEqual(
            pdb.sequence_accession,
            "P01308",
        )

        self.assertEqual(
            pdb.canonical_key,
            (
                "pdb:6B3Q:"
                "uniprot:P01308:"
                "1-110"
            ),
        )

    def test_pdb_chains_are_restricted_to_matched_uniprot(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        pdb = batch.hits[
            0
        ]

        self.assertEqual(
            pdb.chains,
            (
                "a",
                "b",
            ),
        )

        self.assertNotIn(
            "A",
            pdb.chains,
        )

        self.assertNotIn(
            "B",
            pdb.chains,
        )

    def test_pdbe_percent_identity_is_normalized(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        pdb = batch.hits[
            0
        ]

        self.assertEqual(
            pdb.identity,
            1.0,
        )

        self.assertEqual(
            pdb.model_sequence_identity,
            1.0,
        )

        self.assertEqual(
            pdb.sequence_coverage,
            1.0,
        )

        self.assertEqual(
            pdb.model_coverage,
            1.0,
        )

    def test_alphafold_native_plddt_is_not_rescaled(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        alphafold = batch.hits[
            1
        ]

        self.assertEqual(
            alphafold.provider,
            "alphafold-db",
        )

        self.assertEqual(
            alphafold.canonical_key,
            "alphafold:AF-P01308-F1",
        )

        self.assertEqual(
            alphafold.source_type,
            "computational",
        )

        self.assertEqual(
            alphafold.model_type,
            "ab-initio",
        )

        self.assertEqual(
            alphafold.confidence_type,
            "pLDDT",
        )

        self.assertEqual(
            alphafold.confidence_value,
            52.91,
        )

    def test_swissmodel_qmeandisco_stays_native(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        swiss = batch.hits[
            2
        ]

        self.assertEqual(
            swiss.provider,
            "swiss-model",
        )

        self.assertEqual(
            swiss.model_type,
            "template-based",
        )

        self.assertEqual(
            swiss.confidence_type,
            "QMEANDisCo",
        )

        self.assertEqual(
            swiss.confidence_value,
            0.523,
        )

        self.assertEqual(
            swiss.model_coverage,
            0.782,
        )

    def test_coordinate_metadata_is_preserved(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        alphafold = batch.hits[
            1
        ]

        self.assertEqual(
            alphafold.coordinate_format,
            "MMCIF",
        )

        self.assertTrue(
            alphafold.coordinate_url.endswith(
                "AF-P01308-F1-model_v6.cif"
            )
        )

        self.assertEqual(
            alphafold.sequence_start,
            1,
        )

        self.assertEqual(
            alphafold.sequence_end,
            110,
        )

    def test_rows_is_applied_after_normalization(
        self,
    ):
        batch = (
            beacons3d.normalize_sequence_result(
                completed_payload(),
                query_sequence=QUERY,
                rows=2,
            )
        )

        self.assertEqual(
            len(
                batch.hits
            ),
            2,
        )

    def test_query_identity_and_model_identity_are_separate(
        self,
    ):
        payload = completed_payload()

        payload[
            0
        ][
            "hit_hsps"
        ][
            0
        ][
            "hsp_identity"
        ] = 99.1

        payload[
            0
        ][
            "summary"
        ][
            "structures"
        ][
            2
        ][
            "summary"
        ][
            "sequence_identity"
        ] = 0.95

        batch = (
            beacons3d.normalize_sequence_result(
                payload,
                query_sequence=QUERY,
                rows=10,
            )
        )

        swiss = batch.hits[
            2
        ]

        self.assertAlmostEqual(
            swiss.identity,
            0.991,
        )

        self.assertEqual(
            swiss.model_sequence_identity,
            0.95,
        )


class ThreeDBeaconsJobTests(
    SimpleTestCase
):
    def test_submit_sequence_search_returns_job_id(
        self,
    ):
        with mock.patch.object(
            beacons3d,
            "_request_json",
            return_value=(
                200,
                {
                    "job_id": "abc123",
                },
            ),
        ) as request_json:
            job_id = (
                beacons3d.submit_sequence_search(
                    QUERY
                )
            )

        self.assertEqual(
            job_id,
            "abc123",
        )

        self.assertEqual(
            request_json.call_count,
            1,
        )

        self.assertEqual(
            request_json.call_args.args[
                0
            ],
            beacons3d.SEARCH_ENDPOINT,
        )

        self.assertEqual(
            request_json.call_args.kwargs[
                "method"
            ],
            "POST",
        )

        self.assertEqual(
            request_json.call_args.kwargs[
                "payload"
            ][
                "sequence"
            ],
            QUERY,
        )

    def test_completed_result_contract(
        self,
    ):
        with mock.patch.object(
            beacons3d,
            "_request_json",
            return_value=(
                200,
                completed_payload(),
            ),
        ):
            state, payload = (
                beacons3d.get_sequence_search_result(
                    "abc123"
                )
            )

        self.assertEqual(
            state,
            "complete",
        )

        self.assertIsInstance(
            payload,
            list,
        )

    def test_pending_result_contract(
        self,
    ):
        with mock.patch.object(
            beacons3d,
            "_request_json",
            return_value=(
                202,
                {
                    "message": (
                        "Search in progress"
                    ),
                },
            ),
        ):
            state, payload = (
                beacons3d.get_sequence_search_result(
                    "abc123"
                )
            )

        self.assertEqual(
            state,
            "pending",
        )

        self.assertIsNone(
            payload
        )

    def test_bounded_sync_search_pending_then_complete(
        self,
    ):
        with (
            mock.patch.object(
                beacons3d,
                "submit_sequence_search",
                return_value="abc123",
            ),
            mock.patch.object(
                beacons3d,
                "get_sequence_search_result",
                side_effect=[
                    (
                        "pending",
                        None,
                    ),
                    (
                        "complete",
                        completed_payload(),
                    ),
                ],
            ) as result,
            mock.patch.object(
                beacons3d.time,
                "sleep",
            ) as sleep,
        ):
            batch = (
                beacons3d.search_by_sequence(
                    QUERY,
                    rows=3,
                )
            )

        self.assertEqual(
            result.call_count,
            2,
        )

        self.assertEqual(
            sleep.call_count,
            1,
        )

        self.assertEqual(
            len(
                batch.hits
            ),
            3,
        )

    def test_bounded_sync_search_does_not_poll_forever(
        self,
    ):
        with (
            mock.patch.object(
                beacons3d,
                "submit_sequence_search",
                return_value="abc123",
            ),
            mock.patch.object(
                beacons3d,
                "get_sequence_search_result",
                return_value=(
                    "pending",
                    None,
                ),
            ) as result,
            mock.patch.object(
                beacons3d.time,
                "sleep",
            ),
        ):
            with self.assertRaises(
                StructureProviderError
            ):
                beacons3d.search_by_sequence(
                    QUERY,
                    rows=3,
                )

        self.assertEqual(
            result.call_count,
            beacons3d.POLL_ATTEMPTS,
        )

    def test_invalid_sequence_is_rejected_locally(
        self,
    ):
        with self.assertRaises(
            StructureSearchQueryError
        ):
            beacons3d.search_by_sequence(
                "AAA*AAA"
            )

    def test_homolog_beacons_is_not_default_but_exact_is(
        self,
    ):
        provider_keys = tuple(
            provider.key
            for provider
            in DEFAULT_PROVIDERS
        )

        self.assertEqual(
            provider_keys,
            (
                "rcsb",
                "beacons3d-exact",
            ),
        )

        self.assertNotIn(
            "beacons3d",
            provider_keys,
        )
