from __future__ import annotations

from django.test import SimpleTestCase

from core.services.structure_search.models import (
    StructureHit,
)
from core.services.structure_search.normalize import (
    optional_fraction,
    pdb_canonical_key,
    string_tuple,
)


class StructureSearchModelTests(
    SimpleTestCase
):
    def test_pdb_canonical_key_is_provider_neutral(
        self,
    ):
        self.assertEqual(
            pdb_canonical_key(
                "6b3q",
                2,
            ),
            "pdb:6B3Q:2",
        )

    def test_fraction_normalization_accepts_fraction(
        self,
    ):
        self.assertEqual(
            optional_fraction(
                0.95
            ),
            0.95,
        )

    def test_fraction_normalization_accepts_percent(
        self,
    ):
        self.assertEqual(
            optional_fraction(
                95
            ),
            0.95,
        )

    def test_fraction_normalization_rejects_out_of_range(
        self,
    ):
        self.assertIsNone(
            optional_fraction(
                101
            )
        )

        self.assertIsNone(
            optional_fraction(
                -1
            )
        )

    def test_string_tuple_deduplicates_preserving_order(
        self,
    ):
        self.assertEqual(
            string_tuple(
                [
                    "A",
                    "A",
                    "B",
                    "",
                ]
            ),
            (
                "A",
                "B",
            ),
        )

    def test_hit_serializes_json_safe_lists(
        self,
    ):
        hit = StructureHit(
            provider="rcsb",
            provider_name="RCSB PDB",
            source_type="experimental",
            model_type="experimental",
            accession="6B3Q",
            canonical_key="pdb:6B3Q:2",
            entity_id="2",
            identity=1.0,
            sequence_coverage=1.0,
            chains=(
                "a",
                "b",
            ),
            warnings=(
                "example",
            ),
        )

        payload = hit.to_dict()

        self.assertEqual(
            payload[
                "canonical_key"
            ],
            "pdb:6B3Q:2",
        )

        self.assertEqual(
            payload[
                "chains"
            ],
            [
                "a",
                "b",
            ],
        )

        self.assertEqual(
            payload[
                "warnings"
            ],
            [
                "example",
            ],
        )

    def test_invalid_source_type_is_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            StructureHit(
                provider="test",
                provider_name="Test",
                source_type="invalid",
                model_type="other",
                accession="X",
                canonical_key="x:X",
            )
