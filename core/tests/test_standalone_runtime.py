"""Regression tests for the standalone/local-first runtime profile."""

from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse


STANDALONE_RUNTIME = (
    getattr(settings, "BIOBANK_RUNTIME_PROFILE", None)
    == "standalone"
)


@skipUnless(
    STANDALONE_RUNTIME,
    "Standalone runtime contract tests require standalone settings.",
)
class StandaloneSettingsContractTests(SimpleTestCase):
    def test_runtime_profile_is_standalone(self):
        self.assertEqual(
            settings.BIOBANK_RUNTIME_PROFILE,
            "standalone",
        )

    def test_runtime_is_localhost_only_by_default(self):
        expected_hosts = {
            "127.0.0.1",
            "localhost",
            "[::1]",
        }

        effective_hosts = set(
            settings.ALLOWED_HOSTS
        )

        # Django's test environment temporarily adds
        # "testserver" to ALLOWED_HOSTS. It is not part of
        # the standalone runtime configuration.
        test_only_hosts = {
            "testserver",
        }

        self.assertEqual(
            effective_hosts - test_only_hosts,
            expected_hosts,
        )

        self.assertNotIn(
            "*",
            effective_hosts,
        )

        self.assertEqual(
            settings.CSRF_TRUSTED_ORIGINS,
            [],
        )

        self.assertIsNone(
            settings.SECURE_PROXY_SSL_HEADER,
        )

    def test_runtime_has_no_url_prefix(self):
        self.assertIsNone(
            settings.FORCE_SCRIPT_NAME,
        )
        self.assertEqual(
            settings.STATIC_URL,
            "/static/",
        )
        self.assertEqual(
            settings.MEDIA_URL,
            "/media/",
        )

        self.assertEqual(
            reverse("login"),
            "/login/",
        )
        self.assertEqual(
            reverse("logout"),
            "/logout/",
        )
        self.assertEqual(
            reverse("workspace"),
            "/workspace/",
        )

    def test_runtime_uses_sqlite(self):
        database = settings.DATABASES["default"]

        self.assertEqual(
            database["ENGINE"],
            "django.db.backends.sqlite3",
        )

    def test_persistent_roots_are_local(self):
        expected_root = (
            Path.home()
            / ".biobank-local"
        )

        self.assertEqual(
            settings.BIOBANK_LOCAL_ROOT,
            expected_root,
        )
        self.assertEqual(
            settings.BIOBANK_LOCAL_DATABASE_ROOT,
            expected_root / "database",
        )
        self.assertEqual(
            settings.BIOBANK_STORAGE_ROOT,
            expected_root / "storage",
        )
        self.assertEqual(
            Path(settings.MEDIA_ROOT),
            expected_root / "data",
        )

    def test_pam_authentication_is_disabled(self):
        pam_middleware = (
            "core.middleware.pam_remote_user."
            "PamRemoteUserMiddleware"
        )

        self.assertNotIn(
            pam_middleware,
            settings.MIDDLEWARE,
        )

        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS,
            [
                "django.contrib.auth.backends."
                "ModelBackend",
            ],
        )

        self.assertFalse(
            settings.BIOBANK_PAM_SYNC_GROUPS,
        )

    def test_optional_infrastructure_is_disabled(self):
        self.assertFalse(
            settings.BIOBANK_HPC_ENABLED,
        )
        self.assertFalse(
            settings.BIOBANK_JUPYTER_ENABLED,
        )
        self.assertFalse(
            settings.BIOBANK_ONLINE_INTEGRATIONS_ENABLED,
        )
        self.assertFalse(
            settings.BIOBANK_LAB_TOOLS_PROVISION_ON_LOGIN,
        )


@skipUnless(
    STANDALONE_RUNTIME,
    "Standalone authentication tests require standalone settings.",
)
@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers."
        "MD5PasswordHasher",
    ],
)
class StandaloneAuthenticationTests(TestCase):
    username = "__standalone_test_admin__"
    password = "standalone-test-password"

    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_superuser(
                username=self.username,
                email="standalone-test@localhost",
                password=self.password,
            )
        )

    def test_local_password_authentication_and_workspace(self):
        response = self.client.get(
            reverse("login"),
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        authenticated = self.client.login(
            username=self.username,
            password=self.password,
        )

        self.assertTrue(authenticated)

        response = self.client.get(
            reverse("workspace"),
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_logout_returns_to_local_login(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("logout"),
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response["Location"],
            "/login/",
        )
