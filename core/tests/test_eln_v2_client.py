"""No-network tests for the eLabFTW API v2 client."""

from django.test import SimpleTestCase

from core.integrations.eln_v2.client import (
    ElnApiError,
    ElnForbidden,
    ElnReadOnlyClient,
    ElnUnauthorized,
    ElnUnavailable,
    UnixSocketTransport,
)


class FakeTransport:
    def __init__(self, status=200, body=b"[]",
                 content_type="application/json"):
        self.response = (
            status,
            content_type,
            body,
        )
        self.calls = []

    def get(self, path, api_key, timeout, max_bytes):
        self.calls.append({
            "path": path,
            "key": api_key,
            "timeout": timeout,
            "max_bytes": max_bytes,
        })
        return self.response


class ElnV2ClientTests(SimpleTestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.client_api = ElnReadOnlyClient(
            api_key="synthetic-test-key",
            transport=self.transport,
        )

    def test_list_experiments(self):
        result = self.client_api.list_experiments(
            limit=10,
            offset=20,
        )

        self.assertEqual(result, [])
        self.assertEqual(
            self.transport.calls[0]["path"],
            "/api/v2/experiments?limit=10&offset=20",
        )

    def test_list_templates(self):
        result = self.client_api.list_templates()

        self.assertEqual(result, [])
        self.assertTrue(
            self.transport.calls[0]["path"].startswith(
                "/api/v2/experiments_templates?"
            )
        )

    def test_get_experiment(self):
        self.transport.response = (
            200,
            "application/json",
            b'{"id":42,"title":"Synthetic experiment"}',
        )

        result = self.client_api.get_experiment(42)

        self.assertEqual(result["id"], 42)

    def test_unauthorized(self):
        self.transport.response = (
            401,
            "application/json",
            b'{}',
        )

        with self.assertRaises(ElnUnauthorized):
            self.client_api.list_experiments()

    def test_forbidden(self):
        self.transport.response = (
            403,
            "application/json",
            b'{}',
        )

        with self.assertRaises(ElnForbidden):
            self.client_api.list_experiments()

    def test_server_failure(self):
        self.transport.response = (
            503,
            "application/json",
            b'{}',
        )

        with self.assertRaises(ElnUnavailable):
            self.client_api.list_experiments()

    def test_redirect_not_accepted(self):
        self.transport.response = (
            302,
            "text/html",
            b'',
        )

        with self.assertRaises(ElnApiError):
            self.client_api.list_experiments()

    def test_invalid_json(self):
        self.transport.response = (
            200,
            "application/json",
            b'not-json',
        )

        with self.assertRaises(ElnApiError):
            self.client_api.list_experiments()

    def test_invalid_pagination(self):
        with self.assertRaises(ValueError):
            self.client_api.list_experiments(
                limit=1000
            )

        with self.assertRaises(ValueError):
            self.client_api.list_experiments(
                offset=-1
            )

        self.assertEqual(self.transport.calls, [])

    def test_invalid_experiment_id(self):
        with self.assertRaises(ValueError):
            self.client_api.get_experiment(
                "../etc/passwd"
            )

        self.assertEqual(self.transport.calls, [])

    def test_missing_credential_rejected(self):
        with self.assertRaises(ValueError):
            ElnReadOnlyClient(
                api_key="",
                transport=self.transport,
            )

    def test_explicit_transport_required(self):
        with self.assertRaises(TypeError):
            ElnReadOnlyClient(
                api_key="synthetic-test-key",
                transport=None,
            )

    def test_relative_socket_path_rejected(self):
        with self.assertRaises(ValueError):
            UnixSocketTransport(
                "relative/eln.sock"
            )
