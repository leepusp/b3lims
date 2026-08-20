from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from core.services import rcsb_pdb
from core.services.structure_search.base import (
    StructureProviderError,
    StructureSearchQueryError,
)
from core.services.structure_search.providers import (
    rcsb,
)


class StructureSearchRcsbProviderTests(
    SimpleTestCase
):
    def test_normalizes_experimental_hit(
        self,
    ):
        raw = {
            "query_length": 110,
            "total_count": 829,
            "hits": [
                {
                    "identifier": "6B3Q_2",
                    "pdb_id": "6b3q",
                    "entity_id": "2",
                    "score": 1.0,
                    "identity": 1.0,
                    "query_coverage": 1.0,
                    "title": "Insulin structure",
                    "description": "Insulin",
                    "chains": [
                        "a",
                        "b",
                    ],
                    "experimental_method": (
                        "X-RAY DIFFRACTION"
                    ),
                    "resolution": 1.5,
                    "methodology": (
                        "experimental"
                    ),
                    "warnings": [],
                }
            ],
        }

        with mock.patch(
            "core.services.rcsb_pdb."
            "search_pdb_by_sequence",
            return_value=raw,
        ) as search:
            batch = (
                rcsb.search_by_sequence(
                    "A" * 110,
                    rows=10,
                )
            )

        self.assertEqual(
            search.call_count,
            1,
        )

        self.assertEqual(
            search.call_args.kwargs[
                "rows"
            ],
            10,
        )

        self.assertEqual(
            batch.provider,
            "rcsb",
        )

        self.assertEqual(
            batch.query_length,
            110,
        )

        self.assertEqual(
            batch.total_count,
            829,
        )

        self.assertEqual(
            len(
                batch.hits
            ),
            1,
        )

        hit = batch.hits[
            0
        ]

        self.assertEqual(
            hit.provider,
            "rcsb",
        )

        self.assertEqual(
            hit.source_type,
            "experimental",
        )

        self.assertEqual(
            hit.model_type,
            "experimental",
        )

        self.assertEqual(
            hit.accession,
            "6B3Q",
        )

        self.assertEqual(
            hit.entity_id,
            "2",
        )

        self.assertEqual(
            hit.canonical_key,
            "pdb:6B3Q:2",
        )

        self.assertEqual(
            hit.identity,
            1.0,
        )

        self.assertEqual(
            hit.sequence_coverage,
            1.0,
        )

        self.assertEqual(
            hit.coordinate_coverage,
            None,
        )

        self.assertEqual(
            hit.chains,
            (
                "a",
                "b",
            ),
        )

    def test_rcsb_query_error_becomes_common_query_error(
        self,
    ):
        with mock.patch(
            "core.services.rcsb_pdb."
            "search_pdb_by_sequence",
            side_effect=(
                rcsb_pdb.RcsbPdbQueryError(
                    "bad sequence"
                )
            ),
        ):
            with self.assertRaises(
                StructureSearchQueryError
            ):
                rcsb.search_by_sequence(
                    "ABC"
                )

    def test_rcsb_provider_error_becomes_common_provider_error(
        self,
    ):
        with mock.patch(
            "core.services.rcsb_pdb."
            "search_pdb_by_sequence",
            side_effect=(
                rcsb_pdb.RcsbPdbSearchError(
                    "provider timeout"
                )
            ),
        ):
            with self.assertRaises(
                StructureProviderError
            ):
                rcsb.search_by_sequence(
                    "A" * 25
                )

    def test_malformed_hit_is_ignored_without_losing_batch(
        self,
    ):
        raw = {
            "query_length": 25,
            "total_count": 1,
            "hits": [
                {
                    "pdb_id": "",
                    "entity_id": "",
                }
            ],
        }

        with mock.patch(
            "core.services.rcsb_pdb."
            "search_pdb_by_sequence",
            return_value=raw,
        ):
            batch = (
                rcsb.search_by_sequence(
                    "A" * 25
                )
            )

        self.assertEqual(
            batch.total_count,
            1,
        )

        self.assertEqual(
            batch.hits,
            (),
        )
