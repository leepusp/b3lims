"""Protected per-user filesystem storage for Biobank Lab Tools."""

from __future__ import annotations

import os
import pwd
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import (
    ImproperlyConfigured,
    SuspiciousFileOperation,
)
from django.core.files import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


USERNAME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
)
ALLOWED_AREAS = {
    "eln",
    "exports",
    "jupyter",
    "molecular",
    "tmp",
}


class LabToolsStorageError(OSError):
    """Raised when protected Lab Tools storage is unavailable."""


def validate_username(value):
    """Return a strictly validated Unix username."""
    username = str(value or "")

    if username != username.strip() or not USERNAME_RE.fullmatch(
        username
    ):
        raise SuspiciousFileOperation(
            "The Lab Tools owner username is invalid."
        )

    return username


def _allowed_home_roots():
    roots = []

    for raw_root in getattr(
        settings,
        "BIOBANK_LAB_TOOLS_HOME_ROOTS",
        getattr(
            settings,
            "BIOBANK_PAM_HOME_ROOTS",
            ("/home",),
        ),
    ):
        try:
            root = Path(str(raw_root)).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ImproperlyConfigured(
                "A configured Lab Tools home root is unavailable."
            ) from exc

        if not root.is_dir():
            raise ImproperlyConfigured(
                "A configured Lab Tools home root is not a directory."
            )

        roots.append(root)

    if not roots:
        raise ImproperlyConfigured(
            "No Lab Tools home root is configured."
        )

    return tuple(roots)


def user_home_for_username(username):
    """Resolve a real, non-system Unix user's protected home."""
    username = validate_username(username)

    try:
        account = pwd.getpwnam(username)
    except KeyError as exc:
        raise LabToolsStorageError(
            "The Lab Tools owner has no Unix account."
        ) from exc

    minimum_uid = int(
        getattr(
            settings,
            "BIOBANK_PAM_MINIMUM_UID",
            1000,
        )
    )

    if account.pw_name != username or account.pw_uid < minimum_uid:
        raise LabToolsStorageError(
            "The Lab Tools owner is not an eligible Unix user."
        )

    try:
        home = Path(account.pw_dir).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LabToolsStorageError(
            "The Lab Tools owner home is unavailable."
        ) from exc

    if not home.is_dir() or not any(
        home != root and root in home.parents
        for root in _allowed_home_roots()
    ):
        raise LabToolsStorageError(
            "The Lab Tools owner home is outside the allowed roots."
        )

    return home


def _relative_lab_tools_root():
    raw_value = str(
        getattr(
            settings,
            "BIOBANK_LAB_TOOLS_RELATIVE_ROOT",
            "biobank/lab_tools",
        )
    )
    path = PurePosixPath(raw_value)

    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ImproperlyConfigured(
            "BIOBANK_LAB_TOOLS_RELATIVE_ROOT must be a safe relative path."
        )

    return Path(*path.parts)


def user_lab_tools_root(username):
    """Return /home/<user>/biobank/lab_tools for an eligible user."""
    return (
        user_home_for_username(username)
        / _relative_lab_tools_root()
    ).resolve(strict=False)


def _validated_relative_path(value, *, allow_empty=False):
    raw_value = str(value or "")

    if "\\" in raw_value:
        raise SuspiciousFileOperation(
            "Backslashes are not permitted in Lab Tools paths."
        )

    path = PurePosixPath(raw_value)

    if path.is_absolute() or any(
        part in {"", ".", ".."}
        for part in path.parts
    ):
        raise SuspiciousFileOperation(
            "The Lab Tools relative path is invalid."
        )

    if not path.parts:
        if allow_empty:
            return path
        raise SuspiciousFileOperation(
            "The Lab Tools relative path is empty."
        )

    if path.parts[0] not in ALLOWED_AREAS:
        raise SuspiciousFileOperation(
            "The Lab Tools storage area is invalid."
        )

    return path


def protected_user_path(username, relative_path):
    """Resolve a relative artifact path without permitting escape."""
    root = user_lab_tools_root(username)
    relative = _validated_relative_path(relative_path)
    candidate = (root / Path(*relative.parts)).resolve(strict=False)

    if candidate == root or root not in candidate.parents:
        raise SuspiciousFileOperation(
            "The Lab Tools path is outside the protected user root."
        )

    return candidate


def storage_runner():
    runner = Path(
        str(
            getattr(
                settings,
                "BIOBANK_LAB_TOOLS_STORAGE_RUNNER",
                "/usr/local/sbin/biobank-user-storage",
            )
        )
    )

    if not runner.is_absolute():
        raise ImproperlyConfigured(
            "The Lab Tools storage runner path must be absolute."
        )

    return runner


def _run_storage_runner(action, username, relative_path=None):
    username = validate_username(username)
    command = [
        "sudo",
        "-n",
        str(storage_runner()),
        str(action),
        username,
    ]

    if relative_path is not None:
        relative = _validated_relative_path(relative_path)
        command.append(relative.as_posix())

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabToolsStorageError(
            "The protected Lab Tools storage runner is unavailable."
        ) from exc

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Unknown storage runner error."
        )
        raise LabToolsStorageError(
            f"The protected Lab Tools storage runner failed: {message}"
        )

    return completed.stdout.strip()


def ensure_user_lab_tools_storage(username):
    """Provision the fixed per-user Lab Tools directory structure."""
    _run_storage_runner("ensure", username)
    return user_lab_tools_root(username)


def prepare_user_storage_directory(username, relative_path):
    """Create a protected, user-owned artifact directory."""
    relative = _validated_relative_path(relative_path)
    _run_storage_runner(
        "prepare-directory",
        username,
        relative.as_posix(),
    )
    return protected_user_path(username, relative.as_posix())


def claim_user_storage_file(username, relative_path):
    """Transfer final ownership of an uploaded artifact to its user."""
    relative = _validated_relative_path(relative_path)
    _run_storage_runner(
        "claim-file",
        username,
        relative.as_posix(),
    )
    return protected_user_path(username, relative.as_posix())


@deconstructible
class UserHomeLabToolsStorage(Storage):
    """Django storage that maps user-qualified names into Unix homes."""

    user_prefix = "users"
    legacy_prefix = "notebook/"

    def _split_user_name(self, name):
        raw_name = str(name or "")

        if "\\" in raw_name:
            raise SuspiciousFileOperation(
                "Backslashes are not permitted in Lab Tools names."
            )

        path = PurePosixPath(raw_name)

        if (
            path.is_absolute()
            or len(path.parts) < 4
            or path.parts[0] != self.user_prefix
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise SuspiciousFileOperation(
                "The Lab Tools storage name is invalid."
            )

        username = validate_username(path.parts[1])
        relative = PurePosixPath(*path.parts[2:])
        _validated_relative_path(relative.as_posix())
        return username, relative

    def _legacy_path(self, name):
        path = PurePosixPath(str(name or ""))

        if (
            path.is_absolute()
            or not str(path).startswith(self.legacy_prefix)
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise SuspiciousFileOperation(
                "The legacy attachment name is invalid."
            )

        root = Path(settings.MEDIA_ROOT).resolve(strict=False)
        candidate = (
            root / Path(*path.parts)
        ).resolve(strict=False)

        if candidate == root or root not in candidate.parents:
            raise SuspiciousFileOperation(
                "The legacy attachment path escapes MEDIA_ROOT."
            )

        return candidate

    def path(self, name):
        raw_name = str(name or "")

        if raw_name.startswith(self.legacy_prefix):
            return str(self._legacy_path(raw_name))

        username, relative = self._split_user_name(raw_name)
        return str(
            protected_user_path(
                username,
                relative.as_posix(),
            )
        )

    def _open(self, name, mode="rb"):
        return File(open(self.path(name), mode))

    def _save(self, name, content):
        username, relative = self._split_user_name(name)
        relative_name = relative.as_posix()

        ensure_user_lab_tools_storage(username)
        directory = prepare_user_storage_directory(
            username,
            relative.parent.as_posix(),
        )

        if not directory.is_dir():
            raise LabToolsStorageError(
                "The protected upload directory was not created."
            )

        destination = protected_user_path(
            username,
            relative_name,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            descriptor = os.open(destination, flags, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                for chunk in content.chunks():
                    target.write(chunk)

            claim_user_storage_file(
                username,
                relative_name,
            )
        except Exception:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        return str(name)

    def delete(self, name):
        try:
            Path(self.path(name)).unlink()
        except FileNotFoundError:
            pass

    def exists(self, name):
        return Path(self.path(name)).exists()

    def size(self, name):
        return Path(self.path(name)).stat().st_size

    def get_created_time(self, name):
        return datetime.fromtimestamp(
            Path(self.path(name)).stat().st_ctime,
            tz=timezone.utc,
        )

    def get_accessed_time(self, name):
        return datetime.fromtimestamp(
            Path(self.path(name)).stat().st_atime,
            tz=timezone.utc,
        )

    def get_modified_time(self, name):
        return datetime.fromtimestamp(
            Path(self.path(name)).stat().st_mtime,
            tz=timezone.utc,
        )

    def listdir(self, path):
        directory = Path(self.path(path))
        directories = []
        files = []

        for child in directory.iterdir():
            if child.is_dir():
                directories.append(child.name)
            else:
                files.append(child.name)

        return directories, files

    def url(self, name):
        raise ValueError(
            "Lab Tools files are available only through authorized views."
        )


lab_tools_storage = UserHomeLabToolsStorage()
