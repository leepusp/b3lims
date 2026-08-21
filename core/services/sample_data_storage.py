"""Protected per-user filesystem storage for Biobank Sample data."""

from __future__ import annotations

import os
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

from core.services.lab_tools_storage import (
    storage_runner,
    user_home_for_username,
    validate_username,
)


SAMPLE_DIRECTORY_RE = re.compile(
    r"^samples/sample_[0-9]+_[A-Za-z0-9._-]+/files$"
)

SAMPLE_FILE_RE = re.compile(
    r"^samples/sample_[0-9]+_[A-Za-z0-9._-]+/"
    r"files/[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$"
)


class SampleDataStorageError(OSError):
    """Raised when protected per-user Sample storage is unavailable."""


def _safe_component(value, *, fallback, max_length):
    text = str(value or "").strip()

    text = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        text,
    )

    while ".." in text:
        text = text.replace("..", "_")

    text = text.strip("._-")

    if not text:
        text = fallback

    return text[:max_length]


def safe_sample_identifier(value, *, fallback="sample"):
    return _safe_component(
        value,
        fallback=fallback,
        max_length=100,
    )


def safe_sample_filename(filename):
    raw = str(filename or "").replace("\\", "/")
    basename = PurePosixPath(raw).name

    return _safe_component(
        basename,
        fallback="file",
        max_length=200,
    )


def sample_file_upload_name(sample, filename):
    if sample is None or sample.pk is None:
        raise SuspiciousFileOperation(
            "Sample files require a saved Sample."
        )

    owner = getattr(sample, "owner", None)
    username = validate_username(
        getattr(owner, "username", "")
    )

    sample_label = safe_sample_identifier(
        getattr(sample, "sample_id", ""),
        fallback=str(sample.pk),
    )

    filename = safe_sample_filename(filename)

    relative = (
        f"samples/"
        f"sample_{sample.pk}_{sample_label}/"
        f"files/{filename}"
    )

    _validated_sample_file(relative)

    return f"users/{username}/{relative}"


def _relative_sample_data_root():
    raw_value = str(
        getattr(
            settings,
            "BIOBANK_SAMPLE_DATA_RELATIVE_ROOT",
            "biobank/data",
        )
    )

    path = PurePosixPath(raw_value)

    if (
        path.is_absolute()
        or not path.parts
        or any(
            part in {"", ".", ".."}
            for part in path.parts
        )
    ):
        raise ImproperlyConfigured(
            "BIOBANK_SAMPLE_DATA_RELATIVE_ROOT "
            "must be a safe relative path."
        )

    return Path(*path.parts)


def user_sample_data_root(username):
    """Return /home/<user>/biobank/data for an eligible Unix user."""

    return (
        user_home_for_username(username)
        / _relative_sample_data_root()
    ).resolve(strict=False)


def _validated_sample_directory(value):
    raw = str(value or "")

    if (
        "\\" in raw
        or ".." in raw
        or "//" in raw
        or not SAMPLE_DIRECTORY_RE.fullmatch(raw)
    ):
        raise SuspiciousFileOperation(
            "The Sample data directory is invalid."
        )

    return PurePosixPath(raw)


def _validated_sample_file(value):
    raw = str(value or "")

    if (
        "\\" in raw
        or ".." in raw
        or "//" in raw
        or not SAMPLE_FILE_RE.fullmatch(raw)
    ):
        raise SuspiciousFileOperation(
            "The Sample data file path is invalid."
        )

    return PurePosixPath(raw)


def protected_sample_data_path(username, relative_path):
    username = validate_username(username)
    relative = _validated_sample_file(relative_path)

    root = user_sample_data_root(username)

    candidate = (
        root
        / Path(*relative.parts)
    ).resolve(strict=False)

    if candidate == root or root not in candidate.parents:
        raise SuspiciousFileOperation(
            "The Sample data path escaped the protected user root."
        )

    return candidate


def protected_sample_data_directory(username, relative_path):
    username = validate_username(username)
    relative = _validated_sample_directory(relative_path)

    root = user_sample_data_root(username)

    candidate = (
        root
        / Path(*relative.parts)
    ).resolve(strict=False)

    if candidate == root or root not in candidate.parents:
        raise SuspiciousFileOperation(
            "The Sample data directory escaped the protected user root."
        )

    return candidate


def _run_sample_data_runner(
    action,
    username,
    relative_path=None,
):
    username = validate_username(username)

    command = [
        "sudo",
        "-n",
        str(storage_runner()),
        str(action),
        username,
    ]

    if relative_path is not None:
        if action == "prepare-data-directory":
            relative = _validated_sample_directory(
                relative_path
            )
        elif action == "claim-data-file":
            relative = _validated_sample_file(
                relative_path
            )
        else:
            raise SampleDataStorageError(
                "Unsupported Sample data runner action."
            )

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
        raise SampleDataStorageError(
            "The protected Sample data storage runner "
            "is unavailable."
        ) from exc

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Unknown storage runner error."
        )

        raise SampleDataStorageError(
            "The protected Sample data storage runner failed: "
            f"{message}"
        )

    return completed.stdout.strip()


def prepare_sample_data_directory(username, relative_path):
    relative = _validated_sample_directory(
        relative_path
    )

    _run_sample_data_runner(
        "prepare-data-directory",
        username,
        relative.as_posix(),
    )

    return protected_sample_data_directory(
        username,
        relative.as_posix(),
    )


def claim_sample_data_file(username, relative_path):
    relative = _validated_sample_file(
        relative_path
    )

    _run_sample_data_runner(
        "claim-data-file",
        username,
        relative.as_posix(),
    )

    return protected_sample_data_path(
        username,
        relative.as_posix(),
    )


@deconstructible
class UserHomeSampleDataStorage(Storage):
    """
    Strict private storage for SampleFile.

    Every logical name must use:

      users/<username>/samples/
      sample_<pk>_<sample_id>/files/<filename>

    SampleFile deliberately has no MEDIA_ROOT fallback.
    """

    user_prefix = "users"

    def _split_user_name(self, name):
        raw = str(name or "")

        if "\\" in raw:
            raise SuspiciousFileOperation(
                "Backslashes are not permitted "
                "in Sample storage names."
            )

        path = PurePosixPath(raw)

        if (
            path.is_absolute()
            or len(path.parts) != 6
            or path.parts[0] != self.user_prefix
            or path.parts[2] != "samples"
            or path.parts[4] != "files"
            or any(
                part in {"", ".", ".."}
                for part in path.parts
            )
        ):
            raise SuspiciousFileOperation(
                "SampleFile must use protected "
                "per-user Sample storage."
            )

        username = validate_username(
            path.parts[1]
        )

        relative = PurePosixPath(
            *path.parts[2:]
        )

        _validated_sample_file(
            relative.as_posix()
        )

        return username, relative

    def path(self, name):
        username, relative = self._split_user_name(
            name
        )

        return str(
            protected_sample_data_path(
                username,
                relative.as_posix(),
            )
        )

    def _open(self, name, mode="rb"):
        return File(
            open(
                self.path(name),
                mode,
            )
        )

    def _save(self, name, content):
        username, relative = self._split_user_name(
            name
        )

        relative_name = relative.as_posix()

        directory = prepare_sample_data_directory(
            username,
            relative.parent.as_posix(),
        )

        if not directory.is_dir():
            raise SampleDataStorageError(
                "The protected Sample upload directory "
                "was not created."
            )

        destination = protected_sample_data_path(
            username,
            relative_name,
        )

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        )

        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            descriptor = os.open(
                destination,
                flags,
                0o600,
            )

            with os.fdopen(
                descriptor,
                "wb",
            ) as target:
                for chunk in content.chunks():
                    target.write(chunk)

                target.flush()
                os.fsync(
                    target.fileno()
                )

            claim_sample_data_file(
                username,
                relative_name,
            )

        except Exception:
            try:
                destination.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise

        return str(name)

    def delete(self, name):
        try:
            Path(
                self.path(name)
            ).unlink()
        except FileNotFoundError:
            pass

    def exists(self, name):
        return Path(
            self.path(name)
        ).exists()

    def size(self, name):
        return Path(
            self.path(name)
        ).stat().st_size

    def get_created_time(self, name):
        return datetime.fromtimestamp(
            Path(
                self.path(name)
            ).stat().st_ctime,
            tz=timezone.utc,
        )

    def get_accessed_time(self, name):
        return datetime.fromtimestamp(
            Path(
                self.path(name)
            ).stat().st_atime,
            tz=timezone.utc,
        )

    def get_modified_time(self, name):
        return datetime.fromtimestamp(
            Path(
                self.path(name)
            ).stat().st_mtime,
            tz=timezone.utc,
        )

    def url(self, name):
        # Validate the logical name first so legacy/malformed
        # names fail even when URL generation is attempted.
        self._split_user_name(name)

        raise ValueError(
            "Sample files are available only through "
            "authorized download views."
        )


sample_data_storage = UserHomeSampleDataStorage()
