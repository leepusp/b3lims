from __future__ import annotations

import inspect
from unittest import mock

from django.test import SimpleTestCase

from core.services import rcsb_pdb


class RcsbPdbSearchResilienceTests(
    SimpleTestCase
):
    def test_generic_request_contract_is_unchanged(
        self,
    ):
        signature = inspect.signature(
            rcsb_pdb._request_json
        )

        self.assertEqual(
            signature.parameters[
                "timeout"
            ].default,
            20,
        )

        self.assertNotIn(
            "retries",
            signature.parameters,
        )

    def test_search_policy_constants(
        self,
    ):
        self.assertEqual(
            rcsb_pdb.RCSB_SEARCH_TIMEOUT,
            45,
        )

        self.assertEqual(
            rcsb_pdb.RCSB_SEARCH_RETRIES,
            1,
        )

        self.assertEqual(
            rcsb_pdb.RCSB_TRANSIENT_HTTP_STATUS_CODES,
            frozenset(
                {
                    429,
                    502,
                    503,
                    504,
                }
            ),
        )

    def test_transport_failure_is_retried_once(
        self,
    ):
        transient = (
            rcsb_pdb.RcsbPdbSearchError(
                "Could not contact the RCSB PDB "
                "service: simulated timeout"
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                transient,
                {
                    "total_count": 0,
                    "result_set": [],
                },
            ],
        ) as request_json:
            result = (
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )
            )

        self.assertEqual(
            result[
                "result_set"
            ],
            [],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

        for call in request_json.call_args_list:
            self.assertEqual(
                call.args[
                    0
                ],
                rcsb_pdb.SEARCH_ENDPOINT,
            )

            self.assertEqual(
                call.kwargs[
                    "timeout"
                ],
                45,
            )

    def test_http_503_is_retried_once(
        self,
    ):
        transient = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 503."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                transient,
                {
                    "total_count": 0,
                    "result_set": [],
                },
            ],
        ) as request_json:
            result = (
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )
            )

        self.assertEqual(
            result[
                "result_set"
            ],
            [],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

    def test_http_429_is_retried_once(
        self,
    ):
        transient = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 429."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                transient,
                {
                    "total_count": 0,
                    "result_set": [],
                },
            ],
        ) as request_json:
            result = (
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )
            )

        self.assertEqual(
            result[
                "result_set"
            ],
            [],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

    def test_http_502_is_retried_once(
        self,
    ):
        transient = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 502."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                transient,
                {
                    "total_count": 0,
                    "result_set": [],
                },
            ],
        ) as request_json:
            result = (
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )
            )

        self.assertEqual(
            result[
                "result_set"
            ],
            [],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

    def test_http_504_is_retried_once(
        self,
    ):
        transient = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 504."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                transient,
                {
                    "total_count": 0,
                    "result_set": [],
                },
            ],
        ) as request_json:
            result = (
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )
            )

        self.assertEqual(
            result[
                "result_set"
            ],
            [],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

    def test_non_transient_http_400_is_not_retried(
        self,
    ):
        permanent = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 400."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=permanent,
        ) as request_json:
            with self.assertRaises(
                rcsb_pdb.RcsbPdbSearchError
            ):
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )

        self.assertEqual(
            request_json.call_count,
            1,
        )

    def test_second_transient_failure_is_propagated(
        self,
    ):
        first = (
            rcsb_pdb.RcsbPdbSearchError(
                "Could not contact the RCSB PDB "
                "service: first timeout"
            )
        )

        second = (
            rcsb_pdb.RcsbPdbSearchError(
                "Could not contact the RCSB PDB "
                "service: second timeout"
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                first,
                second,
            ],
        ) as request_json:
            with self.assertRaises(
                rcsb_pdb.RcsbPdbSearchError
            ) as context:
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )

        self.assertIn(
            "second timeout",
            str(
                context.exception
            ),
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

    def test_sequence_search_uses_search_wrapper(
        self,
    ):
        with mock.patch(
            "core.services.rcsb_pdb."
            "_request_search_json",
            return_value={
                "total_count": 0,
                "result_set": [],
            },
        ) as search_request:
            result = (
                rcsb_pdb.search_pdb_by_sequence(
                    "A" * 25
                )
            )

        self.assertEqual(
            result[
                "hits"
            ],
            [],
        )

        self.assertEqual(
            search_request.call_count,
            1,
        )

        payload = (
            search_request.call_args.args[
                0
            ]
        )

        self.assertEqual(
            payload[
                "return_type"
            ],
            "polymer_entity",
        )

    def test_coordinate_preview_contract_is_unchanged(
        self,
    ):
        signature = inspect.signature(
            rcsb_pdb.fetch_pdb_mmcif
        )

        self.assertEqual(
            signature.parameters[
                "timeout"
            ].default,
            30,
        )

        self.assertEqual(
            signature.parameters[
                "max_bytes"
            ].default,
            rcsb_pdb.MAX_PDB_PREVIEW_BYTES,
        )


class RcsbPdbInternalSequenceTimeoutTests(
    SimpleTestCase
):
    def test_internal_sequence_search_http_500_is_transient(
        self,
    ):
        error = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 500. "
                "{"
                '"status":500,'
                '"message":"Sequence search server at '
                "'http://production-rcsb-seqsearch-b' "
                "did not complete ticketId "
                "'example-ticket' within 30000 ms "
                '(polled 18 times). Giving up polling."'
                "}"
            )
        )

        self.assertTrue(
            rcsb_pdb._is_transient_search_error(
                error
            )
        )

    def test_internal_sequence_search_http_500_is_retried_once(
        self,
    ):
        internal_timeout = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 500. "
                "Sequence search server at "
                "'http://production-rcsb-seqsearch-b' "
                "did not complete ticketId "
                "'example-ticket' within 30000 ms "
                "(polled 18 times). Giving up polling."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=[
                internal_timeout,
                {
                    "total_count": 0,
                    "result_set": [],
                },
            ],
        ) as request_json:
            result = (
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )
            )

        self.assertEqual(
            result[
                "result_set"
            ],
            [],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

        for call in request_json.call_args_list:
            self.assertEqual(
                call.kwargs[
                    "timeout"
                ],
                45,
            )

    def test_generic_http_500_remains_non_transient(
        self,
    ):
        generic_error = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 500. "
                "Unexpected application failure."
            )
        )

        self.assertFalse(
            rcsb_pdb._is_transient_search_error(
                generic_error
            )
        )

    def test_generic_http_500_is_not_retried(
        self,
    ):
        generic_error = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 500. "
                "Unexpected application failure."
            )
        )

        with mock.patch(
            "core.services.rcsb_pdb._request_json",
            side_effect=generic_error,
        ) as request_json:
            with self.assertRaises(
                rcsb_pdb.RcsbPdbSearchError
            ):
                rcsb_pdb._request_search_json(
                    {
                        "query": "test",
                    }
                )

        self.assertEqual(
            request_json.call_count,
            1,
        )

    def test_sequence_timeout_marker_without_http_500_is_not_enough(
        self,
    ):
        error = (
            rcsb_pdb.RcsbPdbSearchError(
                "RCSB returned HTTP 400. "
                "Sequence search server did not "
                "complete ticketId 'example'. "
                "Giving up polling."
            )
        )

        self.assertFalse(
            rcsb_pdb._is_transient_search_error(
                error
            )
        )
