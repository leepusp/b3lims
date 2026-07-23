from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


class PamRemoteUserMiddlewareTests(TestCase):
    def setUp(self):
        self.home_root = (
            Path("/tmp")
            / f"biobank-pam-tests-{self._testMethodName}"
        )
        self.home_root.mkdir(
            parents=True,
            exist_ok=False,
        )

        self.settings_override = override_settings(
            BIOBANK_PAM_HOME_ROOTS=(
                str(self.home_root),
            ),
            BIOBANK_PAM_TRUSTED_PROXIES=(
                "127.0.0.1",
                "::1",
            ),
            BIOBANK_PAM_MINIMUM_UID=1000,
        )
        self.settings_override.enable()

        self.addCleanup(
            self.settings_override.disable
        )
        self.addCleanup(
            self._remove_home_root
        )

    def _remove_home_root(self):
        for child in sorted(
            self.home_root.rglob("*"),
            reverse=True,
        ):
            if child.is_dir():
                child.rmdir()
            else:
                child.unlink()

        if self.home_root.exists():
            self.home_root.rmdir()

    def _account(
        self,
        username,
        *,
        uid=12000,
        shell="/bin/bash",
    ):
        home = self.home_root / username
        home.mkdir(exist_ok=True)

        return SimpleNamespace(
            pw_name=username,
            pw_uid=uid,
            pw_gid=uid,
            pw_dir=str(home),
            pw_shell=shell,
        )

    def _request(self, username, **extra):
        headers = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_X_BIOBANK_PAM_USER": username,
        }
        headers.update(extra)

        return self.client.get(
            "/login/",
            **headers,
        )

    @patch(
        "core.middleware.pam_remote_user.pwd.getpwnam"
    )
    def test_pam_identity_creates_and_logs_in_django_user(
        self,
        mocked_getpwnam,
    ):
        mocked_getpwnam.return_value = self._account(
            "pamuser"
        )

        response = self._request("pamuser")

        self.assertEqual(response.status_code, 302)

        user = get_user_model().objects.get(
            username="pamuser"
        )

        self.assertEqual(
            int(
                self.client.session[
                    "_auth_user_id"
                ]
            ),
            user.id,
        )

    def test_request_without_pam_header_preserves_session(self):
        user = get_user_model().objects.create_user(
            username="existing-user",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get(
            "/login/",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            int(
                self.client.session[
                    "_auth_user_id"
                ]
            ),
            user.id,
        )

    @patch(
        "core.middleware.pam_remote_user.pwd.getpwnam"
    )
    def test_pam_identity_replaces_different_django_session(
        self,
        mocked_getpwnam,
    ):
        local_user = (
            get_user_model().objects.create_user(
                username="different-user",
                password="test-password",
            )
        )
        self.client.force_login(local_user)

        mocked_getpwnam.return_value = self._account(
            "pamuser"
        )

        response = self._request("pamuser")

        self.assertEqual(response.status_code, 302)

        pam_user = get_user_model().objects.get(
            username="pamuser"
        )

        self.assertEqual(
            int(
                self.client.session[
                    "_auth_user_id"
                ]
            ),
            pam_user.id,
        )

    def test_untrusted_proxy_cannot_supply_pam_identity(self):
        response = self._request(
            "pamuser",
            REMOTE_ADDR="192.0.2.20",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            get_user_model().objects.filter(
                username="pamuser"
            ).exists()
        )

    def test_invalid_pam_username_is_rejected(self):
        response = self._request(
            "../../root"
        )

        self.assertEqual(response.status_code, 403)

    @patch(
        "core.middleware.pam_remote_user.pwd.getpwnam",
        side_effect=KeyError,
    )
    def test_missing_unix_account_is_rejected(
        self,
        mocked_getpwnam,
    ):
        response = self._request(
            "missinguser"
        )

        self.assertEqual(response.status_code, 403)
        mocked_getpwnam.assert_called_once_with(
            "missinguser"
        )

    @patch(
        "core.middleware.pam_remote_user.pwd.getpwnam"
    )
    def test_system_account_is_rejected(
        self,
        mocked_getpwnam,
    ):
        mocked_getpwnam.return_value = self._account(
            "serviceuser",
            uid=975,
            shell="/sbin/nologin",
        )

        response = self._request(
            "serviceuser"
        )

        self.assertEqual(response.status_code, 403)
