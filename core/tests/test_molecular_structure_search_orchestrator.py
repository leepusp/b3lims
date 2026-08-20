from __future__ import annotations

from django.test import SimpleTestCase

from core.services.structure_search.base import (
    StructureProviderError,
)
from core.services.structure_search.models import (
    ProviderSearchBatch,
    StructureHit,
)
from core.services.structure_search.search import (
    search_structures_by_sequence,
)


def pdb_hit(
    *,
    provider,
    provider_name,
    pdb_id="6B3Q",
    entity_id="2",
):
    return StructureHit(
        provider=provider,
        provider_name=provider_name,
        source_type="experimental",
        model_type="experimental",
        accession=pdb_id,
        canonical_key=(
            f"pdb:{pdb_id}:{entity_id}"
        ),
        entity_id=entity_id,
    )


class _PrimaryProvider:
    key = "rcsb"
    display_name = "RCSB PDB"

    @staticmethod
    def search_by_sequence(
        sequence,
        *,
        rows=10,
    ):
        return ProviderSearchBatch(
            provider="rcsb",
            provider_name="RCSB PDB",
            query_length=len(
                sequence
            ),
            total_count=1,
            hits=(
                pdb_hit(
                    provider="rcsb",
                    provider_name=(
                        "RCSB PDB"
                    ),
                ),
            ),
        )


class _DuplicateProvider:
    key = "beacons3d"
    display_name = "3D-Beacons"

    @staticmethod
    def search_by_sequence(
        sequence,
        *,
        rows=10,
    ):
        return ProviderSearchBatch(
            provider="beacons3d",
            provider_name="3D-Beacons",
            query_length=len(
                sequence
            ),
            total_count=2,
            hits=(
                pdb_hit(
                    provider="beacons3d",
                    provider_name=(
                        "3D-Beacons"
                    ),
                ),
                StructureHit(
                    provider="beacons3d",
                    provider_name=(
                        "3D-Beacons"
                    ),
                    source_type=(
                        "computational"
                    ),
                    model_type="ab-initio",
                    accession=(
                        "AF-P01308-F1"
                    ),
                    canonical_key=(
                        "alphafold:"
                        "AF-P01308-F1"
                    ),
                ),
            ),
        )


class _DegradedProvider:
    key = "degraded"
    display_name = "Degraded Provider"

    @staticmethod
    def search_by_sequence(
        sequence,
        *,
        rows=10,
    ):
        raise StructureProviderError(
            "temporary provider failure"
        )


class StructureSearchOrchestratorTests(
    SimpleTestCase
):
    def test_first_provider_wins_duplicate_pdb_entity(
        self,
    ):
        result = (
            search_structures_by_sequence(
                "A" * 110,
                providers=(
                    _PrimaryProvider,
                    _DuplicateProvider,
                ),
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
                0
            ].provider,
            "rcsb",
        )

        self.assertEqual(
            result.hits[
                1
            ].canonical_key,
            "alphafold:AF-P01308-F1",
        )

    def test_degraded_provider_does_not_erase_available_results(
        self,
    ):
        result = (
            search_structures_by_sequence(
                "A" * 25,
                providers=(
                    _DegradedProvider,
                    _PrimaryProvider,
                ),
            )
        )

        self.assertEqual(
            len(
                result.hits
            ),
            1,
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

    def test_all_degraded_still_returns_provider_reports(
        self,
    ):
        result = (
            search_structures_by_sequence(
                "A" * 25,
                providers=(
                    _DegradedProvider,
                ),
            )
        )

        self.assertEqual(
            result.query_length,
            25,
        )

        self.assertEqual(
            result.hits,
            (),
        )

        self.assertEqual(
            result.providers[
                0
            ].state,
            "degraded",
        )

    def test_all_degraded_normalizes_query_whitespace(
        self,
    ):
        result = (
            search_structures_by_sequence(
                "AAAAA\nAAAAA",
                providers=(
                    _DegradedProvider,
                ),
            )
        )

        self.assertEqual(
            result.query_length,
            10,
        )

    def test_result_serialization_is_json_safe(
        self,
    ):
        result = (
            search_structures_by_sequence(
                "A" * 25,
                providers=(
                    _PrimaryProvider,
                ),
            )
        )

        payload = result.to_dict()

        self.assertEqual(
            payload[
                "query_length"
            ],
            25,
        )

        self.assertEqual(
            payload[
                "returned_count"
            ],
            1,
        )

        self.assertEqual(
            payload[
                "providers"
            ][
                0
            ][
                "state"
            ],
            "available",
        )
