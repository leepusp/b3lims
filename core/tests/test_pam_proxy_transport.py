from django.test import (
    RequestFactory,
    SimpleTestCase,
    override_settings,
)

from core.middleware.pam_remote_user import (
    _trusted_proxy,
)


class PamProxyTransportTrustTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request_with_remote_addr(self, remote_addr):
        request = self.factory.get("/b3lims/workspace/")
        request.META["REMOTE_ADDR"] = remote_addr
        return request

    @override_settings(
        BIOBANK_PAM_TRUST_UNIX_SOCKET=False,
        BIOBANK_PAM_TRUSTED_PROXIES=(),
    )
    def test_empty_remote_addr_rejected_by_default(self):
        request = self.request_with_remote_addr("")

        self.assertFalse(
            _trusted_proxy(request)
        )

    @override_settings(
        BIOBANK_PAM_TRUST_UNIX_SOCKET=True,
        BIOBANK_PAM_TRUSTED_PROXIES=(),
    )
    def test_empty_remote_addr_trusted_when_uds_enabled(self):
        request = self.request_with_remote_addr("")

        self.assertTrue(
            _trusted_proxy(request)
        )

    @override_settings(
        BIOBANK_PAM_TRUST_UNIX_SOCKET=True,
        BIOBANK_PAM_TRUSTED_PROXIES=(),
    )
    def test_uds_trust_does_not_trust_loopback_tcp(self):
        request = self.request_with_remote_addr(
            "127.0.0.1"
        )

        self.assertFalse(
            _trusted_proxy(request)
        )

    @override_settings(
        BIOBANK_PAM_TRUST_UNIX_SOCKET=False,
        BIOBANK_PAM_TRUSTED_PROXIES=(
            "127.0.0.1",
        ),
    )
    def test_loopback_requires_explicit_proxy_trust(self):
        request = self.request_with_remote_addr(
            "127.0.0.1"
        )

        self.assertTrue(
            _trusted_proxy(request)
        )

    @override_settings(
        BIOBANK_PAM_TRUST_UNIX_SOCKET=True,
        BIOBANK_PAM_TRUSTED_PROXIES=(),
    )
    def test_uds_trust_does_not_trust_remote_tcp(self):
        request = self.request_with_remote_addr(
            "192.0.2.20"
        )

        self.assertFalse(
            _trusted_proxy(request)
        )
