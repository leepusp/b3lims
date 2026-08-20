from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from core.services.structure_search.models import (
    ProviderSearchBatch,
    StructureHit,
)
from core.services.structure_search.providers import (
    beacons3d,
    beacons3d_exact,
    rcsb,
)
from core.services.structure_search.search import (
    DEFAULT_PROVIDERS,
    search_structures_by_sequence,
)


QUERY = (
    "MALWMRLLPLLALLALWGPDPAAA"
    "FVNQHLCGSHLVEALYLVCGERG"
    "FFYTPKTRREAEDLQVGQVELGG"
    "GPGAGSLQPLALEGSLQKRGIVE"
    "QCCTSICSLYQLENYCN"
)


def exact_summary_payload():
    return {
        "entry": {
            "sequence": QUERY,
            "checksum": (
                "12e9c9e4e2835c302e8ba615115edda3"
            ),
            "checksum_type": "MD5",
        },
        "structures": [
            {
                "summary": {
                    "model_identifier": (
                        "12e9c9e4e2835c302e8ba615115edda3"
                        "_25-110:2lwz.1.A"
                    ),
                    "provider": "SWISS-MODEL",
                    "model_category": (
                        "TEMPLATE-BASED"
                    ),
                    "model_type": "ATOMIC",
                    "model_format": "MMCIF",
                    "model_url": (
                        "https://swissmodel.example/"
                        "model.cif"
                    ),
                    "model_page_url": (
                        "https://swissmodel.example/"
                        "model"
                    ),
                    "sequence_identity": 1.0,
                    "coverage": 0.782,
                    "uniprot_start": 25,
                    "uniprot_end": 110,
                    "confidence_type": (
                        "QMEANDisCo"
                    ),
                    "confidence_avg_local_score": (
                        0.523
                    ),
                    "entities": [
                        {
                            "entity_type": "POLYMER",
                            "description": (
                                "Insulin model"
                            ),
                            "chain_ids": [
                                "A",
                            ],
                            "identifier": None,
                            "identifier_category": None,
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
                        "AF-P01308-F1"
                    ),
                    "provider": "AlphaFold DB",
                    "model_category": "AB-INITIO",
                    "model_type": "ATOMIC",
                    "model_format": "MMCIF",
                    "model_url": (
                        "https://alphafold.ebi.ac.uk/"
                        "files/AF-P01308-F1-"
                        "model_v6.cif"
                    ),
                    "model_page_url": (
                        "https://alphafold.ebi.ac.uk/"
                        "entry/AF-P01308-F1"
                    ),
                    "sequence_identity": 1.0,
                    "coverage": 1.0,
                    "uniprot_start": 1,
                    "uniprot_end": 110,
                    "confidence_type": "pLDDT",
                    "confidence_avg_local_score": (
                        52.91
                    ),
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
                #
                # Deliberately experimental: exact default
                # normalization must exclude it because RCSB is
                # responsible for experimental structures.
                #
                "summary": {
                    "model_identifier": "6b3q",
                    "provider": "PDBe",
                    "model_category": (
                        "EXPERIMENTALLY DETERMINED"
                    ),
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
                    "resolution": 3.7,
                    "experimental_method": (
                        "ELECTRON MICROSCOPY"
                    ),
                    "entities": [
                        {
                            "entity_type": "POLYMER",
                            "description": "Insulin",
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
                        }
                    ],
                }
            },
        ],
    }


class ThreeDBeaconsExactSummaryTests(
    SimpleTestCase
):
    def test_exact_summary_url_uses_sequence_and_type(
        self,
    ):
        with mock.patch.object(
            beacons3d,
            "_request_json",
            return_value=(
                200,
                exact_summary_payload(),
            ),
        ) as request_json:
            payload = (
                beacons3d.get_exact_sequence_summary(
                    QUERY
                )
            )

        self.assertIn(
            "structures",
            payload,
        )

        url = request_json.call_args.args[
            0
        ]

        self.assertTrue(
            url.startswith(
                beacons3d.SUMMARY_ENDPOINT
                + "?"
            )
        )

        self.assertIn(
            "type=sequence",
            url,
        )

        self.assertIn(
            "id=",
            url,
        )

    def test_exact_default_keeps_computational_only(
        self,
    ):
        batch = (
            beacons3d.normalize_exact_sequence_summary(
                exact_summary_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        self.assertEqual(
            batch.total_count,
            2,
        )

        self.assertEqual(
            len(
                batch.hits
            ),
            2,
        )

        self.assertEqual(
            tuple(
                hit.provider
                for hit in batch.hits
            ),
            (
                "swiss-model",
                "alphafold-db",
            ),
        )

        self.assertNotIn(
            "pdbe",
            tuple(
                hit.provider
                for hit in batch.hits
            ),
        )

    def test_exact_query_identity_is_one(
        self,
    ):
        batch = (
            beacons3d.normalize_exact_sequence_summary(
                exact_summary_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        for hit in batch.hits:
            self.assertEqual(
                hit.identity,
                1.0,
            )

            self.assertEqual(
                hit.sequence_coverage,
                1.0,
            )

    def test_exact_alphafold_metadata(
        self,
    ):
        batch = (
            beacons3d.normalize_exact_sequence_summary(
                exact_summary_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        alphafold = next(
            hit
            for hit in batch.hits
            if hit.provider
            == "alphafold-db"
        )

        self.assertEqual(
            alphafold.sequence_accession,
            "P01308",
        )

        self.assertEqual(
            alphafold.canonical_key,
            "alphafold:AF-P01308-F1",
        )

        self.assertEqual(
            alphafold.confidence_type,
            "pLDDT",
        )

        self.assertEqual(
            alphafold.confidence_value,
            52.91,
        )

        self.assertEqual(
            alphafold.chains,
            (
                "A",
            ),
        )

    def test_exact_swissmodel_native_quality(
        self,
    ):
        batch = (
            beacons3d.normalize_exact_sequence_summary(
                exact_summary_payload(),
                query_sequence=QUERY,
                rows=10,
            )
        )

        swiss = next(
            hit
            for hit in batch.hits
            if hit.provider
            == "swiss-model"
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

    def test_exact_rows_does_not_destroy_total_count(
        self,
    ):
        batch = (
            beacons3d.normalize_exact_sequence_summary(
                exact_summary_payload(),
                query_sequence=QUERY,
                rows=1,
            )
        )

        self.assertEqual(
            batch.total_count,
            2,
        )

        self.assertEqual(
            len(
                batch.hits
            ),
            1,
        )

    def test_exact_search_does_not_submit_homology_job(
        self,
    ):
        with (
            mock.patch.object(
                beacons3d,
                "get_exact_sequence_summary",
                return_value=(
                    exact_summary_payload()
                ),
            ),
            mock.patch.object(
                beacons3d,
                "submit_sequence_search",
            ) as submit,
        ):
            batch = (
                beacons3d.search_exact_models_by_sequence(
                    QUERY,
                    rows=10,
                )
            )

        self.assertEqual(
            len(
                batch.hits
            ),
            2,
        )

        submit.assert_not_called()


class ThreeDBeaconsExactAdapterTests(
    SimpleTestCase
):
    def test_exact_adapter_has_separate_provider_identity(
        self,
    ):
        source_batch = ProviderSearchBatch(
            provider="beacons3d",
            provider_name="3D-Beacons",
            query_length=110,
            total_count=1,
            hits=(
                StructureHit(
                    provider="alphafold-db",
                    provider_name="AlphaFold DB",
                    discovery_provider="beacons3d",
                    source_type="computational",
                    model_type="ab-initio",
                    accession="AF-P01308-F1",
                    canonical_key=(
                        "alphafold:"
                        "AF-P01308-F1"
                    ),
                ),
            ),
        )

        with mock.patch.object(
            beacons3d,
            "search_exact_models_by_sequence",
            return_value=source_batch,
        ):
            batch = (
                beacons3d_exact.search_by_sequence(
                    QUERY
                )
            )

        self.assertEqual(
            batch.provider,
            "beacons3d-exact",
        )

        self.assertEqual(
            batch.provider_name,
            "3D-Beacons exact models",
        )

        self.assertEqual(
            batch.hits[
                0
            ].provider,
            "alphafold-db",
        )

    def test_default_provider_order(
        self,
    ):
        self.assertEqual(
            tuple(
                provider.key
                for provider
                in DEFAULT_PROVIDERS
            ),
            (
                "rcsb",
                "beacons3d-exact",
            ),
        )

        self.assertNotIn(
            beacons3d,
            DEFAULT_PROVIDERS,
        )


class UnifiedDefaultStructureSearchTests(
    SimpleTestCase
):
    def test_default_combines_experimental_and_exact_predicted(
        self,
    ):
        rcsb_batch = ProviderSearchBatch(
            provider="rcsb",
            provider_name="RCSB PDB",
            query_length=110,
            total_count=1,
            hits=(
                StructureHit(
                    provider="rcsb",
                    provider_name="RCSB PDB",
                    source_type="experimental",
                    model_type="experimental",
                    accession="6B3Q",
                    canonical_key="pdb:6B3Q:2",
                    entity_id="2",
                    identity=1.0,
                    sequence_coverage=1.0,
                ),
            ),
        )

        exact_batch = ProviderSearchBatch(
            provider="beacons3d-exact",
            provider_name=(
                "3D-Beacons exact models"
            ),
            query_length=110,
            total_count=1,
            hits=(
                StructureHit(
                    provider="alphafold-db",
                    provider_name="AlphaFold DB",
                    discovery_provider="beacons3d",
                    source_type="computational",
                    model_type="ab-initio",
                    accession="AF-P01308-F1",
                    canonical_key=(
                        "alphafold:"
                        "AF-P01308-F1"
                    ),
                    confidence_type="pLDDT",
                    confidence_value=52.91,
                ),
            ),
        )

        with (
            mock.patch.object(
                rcsb,
                "search_by_sequence",
                return_value=rcsb_batch,
            ),
            mock.patch.object(
                beacons3d_exact,
                "search_by_sequence",
                return_value=exact_batch,
            ),
        ):
            result = (
                search_structures_by_sequence(
                    QUERY,
                    rows=10,
                )
            )

        self.assertEqual(
            len(
                result.hits
            ),
            2,
        )

        self.assertEqual(
            result.hits[
                0
            ].canonical_key,
            "pdb:6B3Q:2",
        )

        self.assertEqual(
            result.hits[
                1
            ].canonical_key,
            "alphafold:AF-P01308-F1",
        )

        self.assertEqual(
            tuple(
                report.state
                for report
                in result.providers
            ),
            (
                "available",
                "available",
            ),
        )

    def test_rcsb_degradation_still_allows_exact_models(
        self,
    ):
        exact_batch = ProviderSearchBatch(
            provider="beacons3d-exact",
            provider_name=(
                "3D-Beacons exact models"
            ),
            query_length=110,
            total_count=1,
            hits=(
                StructureHit(
                    provider="alphafold-db",
                    provider_name="AlphaFold DB",
                    discovery_provider="beacons3d",
                    source_type="computational",
                    model_type="ab-initio",
                    accession="AF-P01308-F1",
                    canonical_key=(
                        "alphafold:"
                        "AF-P01308-F1"
                    ),
                ),
            ),
        )

        from core.services.structure_search.base import (
            StructureProviderError,
        )

        with (
            mock.patch.object(
                rcsb,
                "search_by_sequence",
                side_effect=(
                    StructureProviderError(
                        "RCSB degraded"
                    )
                ),
            ),
            mock.patch.object(
                beacons3d_exact,
                "search_by_sequence",
                return_value=exact_batch,
            ),
        ):
            result = (
                search_structures_by_sequence(
                    QUERY
                )
            )

        self.assertEqual(
            len(
                result.hits
            ),
            1,
        )

        self.assertEqual(
            result.hits[
                0
            ].provider,
            "alphafold-db",
        )

        self.assertEqual(
            result.providers[
                0
            ].state,
            "degraded",
        )

        self.assertEqual(
            result.providers[
                1
            ].state,
            "available",
        )
