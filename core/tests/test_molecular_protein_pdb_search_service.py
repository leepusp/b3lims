from unittest.mock import patch

from django.test import SimpleTestCase

from core.services.rcsb_pdb import (
    RcsbPdbQueryError,
    normalize_protein_sequence,
    search_pdb_by_sequence,
)


class RcsbPdbSearchServiceTests(
    SimpleTestCase
):
    def test_short_sequence_is_rejected(self):
        with self.assertRaises(
            RcsbPdbQueryError
        ):
            normalize_protein_sequence(
                "M" * 24
            )

    def test_invalid_residue_is_rejected(self):
        with self.assertRaises(
            RcsbPdbQueryError
        ):
            normalize_protein_sequence(
                ("M" * 30) + "*"
            )

    @patch(
        "core.services.rcsb_pdb._request_json"
    )
    def test_search_builds_experimental_sequence_query(
        self,
        request_json,
    ):
        calls = []

        def fake(
            url,
            *,
            payload=None,
            timeout=20,
        ):
            calls.append(
                {
                    "url": url,
                    "payload": payload,
                }
            )

            if "rcsbsearch" in url:
                return {
                    "total_count": 1,
                    "result_set": [
                        {
                            "identifier": "1ABC_1",
                            "score": 1.0,
                            "services": [
                                {
                                    "node_id": 0,
                                    "original_score": 100,
                                    "norm_score": 1,
                                    "match_context": [
                                        {
                                            "sequence_identity": 1.0,
                                            "evalue": 0.0,
                                            "bitscore": 100,
                                            "query_beg": 1,
                                            "query_end": 30,
                                            "subject_beg": 5,
                                            "subject_end": 34,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }

            if "/polymer_entity/" in url:
                return {
                    "entity_poly": {
                        "pdbx_seq_one_letter_code_can": (
                            "M" * 30
                        ),
                    },
                    "rcsb_polymer_entity": {
                        "pdbx_description": (
                            "QA Protein"
                        ),
                    },
                    "rcsb_polymer_entity_container_identifiers": {
                        "auth_asym_ids": [
                            "A",
                        ],
                        "asym_ids": [
                            "A",
                        ],
                    },
                }

            if "/entry/" in url:
                return {
                    "struct": {
                        "title": (
                            "QA experimental structure"
                        ),
                    },
                    "exptl": [
                        {
                            "method": (
                                "X-RAY DIFFRACTION"
                            ),
                        },
                    ],
                    "rcsb_entry_info": {
                        "experimental_method": (
                            "X-ray"
                        ),
                        "resolution_combined": [
                            1.8,
                        ],
                        "structure_determination_methodology": (
                            "experimental"
                        ),
                    },
                }

            raise AssertionError(
                f"Unexpected URL: {url}"
            )

        request_json.side_effect = fake

        result = search_pdb_by_sequence(
            "M" * 30,
            identity_cutoff=0.9,
            evalue_cutoff=0.1,
            rows=5,
        )

        self.assertEqual(
            result[
                "total_count"
            ],
            1,
        )

        self.assertEqual(
            len(
                result[
                    "hits"
                ]
            ),
            1,
        )

        hit = result[
            "hits"
        ][0]

        self.assertEqual(
            hit[
                "pdb_id"
            ],
            "1ABC",
        )

        self.assertEqual(
            hit[
                "entity_id"
            ],
            "1",
        )

        self.assertEqual(
            hit[
                "chains"
            ],
            [
                "A",
            ],
        )

        self.assertEqual(
            hit[
                "identity"
            ],
            1.0,
        )

        self.assertEqual(
            hit[
                "query_coverage"
            ],
            1.0,
        )

        self.assertEqual(
            hit[
                "resolution"
            ],
            1.8,
        )

        search_call = calls[0]

        payload = search_call[
            "payload"
        ]

        self.assertEqual(
            payload[
                "return_type"
            ],
            "polymer_entity",
        )

        self.assertEqual(
            payload[
                "request_options"
            ][
                "results_content_type"
            ],
            [
                "experimental",
            ],
        )

        self.assertEqual(
            payload[
                "query"
            ][
                "parameters"
            ][
                "identity_cutoff"
            ],
            0.9,
        )
