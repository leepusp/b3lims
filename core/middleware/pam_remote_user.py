"""Trusted PAM remote-user bridge for the Biobank application."""

from __future__ import annotations

import pwd
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied


PAM_USERNAME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
)

BLOCKED_SHELLS = {
    "/bin/false",
    "/sbin/nologin",
    "/usr/bin/false",
    "/usr/sbin/nologin",
}


@dataclass(frozen=True)
class PamIdentity:
    """Validated correspondence between PAM, Unix and Django."""

    username: str
    uid: int
    gid: int
    home: Path
    shell: str


def _permission_denied(message):
    raise PermissionDenied(message)


def _trusted_proxy(request):
    remote_address = str(
        request.META.get("REMOTE_ADDR") or ""
    ).strip()

    trusted = {
        str(value).strip()
        for value in getattr(
            settings,
            "BIOBANK_PAM_TRUSTED_PROXIES",
            ("127.0.0.1", "::1"),
        )
        if str(value).strip()
    }

    return remote_address in trusted


def _allowed_home_roots():
    roots = []

    for raw_root in getattr(
        settings,
        "BIOBANK_PAM_HOME_ROOTS",
        ("/home",),
    ):
        root = Path(str(raw_root)).resolve(
            strict=True
        )

        if not root.is_dir():
            _permission_denied(
                "The configured PAM home root is invalid."
            )

        roots.append(root)

    if not roots:
        _permission_denied(
            "No PAM home root is configured."
        )

    return tuple(roots)


def _validated_identity(raw_username):
    username = str(raw_username or "")

    if username != username.strip():
        _permission_denied(
            "The PAM username contains invalid whitespace."
        )

    if not PAM_USERNAME_RE.fullmatch(username):
        _permission_denied(
            "The PAM username is invalid."
        )

    try:
        account = pwd.getpwnam(username)
    except KeyError:
        _permission_denied(
            "The PAM user has no Unix account."
        )

    if account.pw_name != username:
        _permission_denied(
            "The PAM and Unix usernames do not match."
        )

    minimum_uid = int(
        getattr(
            settings,
            "BIOBANK_PAM_MINIMUM_UID",
            1000,
        )
    )

    if account.pw_uid < minimum_uid:
        _permission_denied(
            "System accounts cannot use PAM application login."
        )

    shell = str(account.pw_shell or "").strip()

    if shell in BLOCKED_SHELLS:
        _permission_denied(
            "The Unix account does not permit interactive access."
        )

    try:
        home = Path(account.pw_dir).resolve(
            strict=True
        )
    except (OSError, RuntimeError):
        _permission_denied(
            "The Unix home directory is unavailable."
        )

    if not home.is_dir():
        _permission_denied(
            "The Unix home path is not a directory."
        )

    allowed = any(
        home != root and root in home.parents
        for root in _allowed_home_roots()
    )

    if not allowed:
        _permission_denied(
            "The Unix home is outside the allowed roots."
        )

    return PamIdentity(
        username=username,
        uid=account.pw_uid,
        gid=account.pw_gid,
        home=home,
        shell=shell,
    )


class PamRemoteUserMiddleware:
    """
    Authenticate the Apache-verified PAM identity in Django.

    The incoming header is trusted only from the loopback reverse
    proxy. Apache must remove any client-supplied value and create
    the header from its authenticated REMOTE_USER value.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.pam_identity = None
        request.pam_username = ""
        request.pam_home = None

        meta_key = str(
            getattr(
                settings,
                "BIOBANK_PAM_REMOTE_USER_META_KEY",
                "HTTP_X_BIOBANK_PAM_USER",
            )
        )

        raw_username = request.META.get(meta_key)

        # During the controlled migration, requests without the PAM
        # header retain the existing Django session behavior.
        if raw_username in {None, ""}:
            return self.get_response(request)

        if not _trusted_proxy(request):
            _permission_denied(
                "PAM identity was received from an untrusted proxy."
            )

        identity = _validated_identity(
            raw_username
        )

        current_username = (
            request.user.get_username()
            if request.user.is_authenticated
            else ""
        )

        if (
            request.user.is_authenticated
            and current_username != identity.username
        ):
            logout(request)

        if (
            not request.user.is_authenticated
            or request.user.get_username()
            != identity.username
        ):
            user = authenticate(
                request,
                remote_user=identity.username,
            )

            if user is None or not user.is_active:
                _permission_denied(
                    "The PAM identity could not be authenticated."
                )

            login(request, user)

        request.pam_identity = identity
        request.pam_username = identity.username
        request.pam_home = identity.home

        return self.get_response(request)
