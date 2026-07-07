from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.utils import timezone


MANIFEST_PATH = Path(
    "/home/public/apps/biobank/storage/backups/media/manifests/media_backups.tsv"
)


@dataclass
class MediaBackupStatus:
    configured: bool
    latest_status: str | None = None
    latest_timestamp: str | None = None
    latest_archive: str | None = None
    latest_archive_bytes: int | None = None
    latest_source_file_count: int | None = None
    latest_source_bytes: int | None = None
    latest_sha256: str | None = None
    latest_age_hours: float | None = None
    error: str | None = None


def _parse_timestamp(value: str):
    try:
        naive = datetime.strptime(value, "%Y%m%d_%H%M%S")
        return timezone.make_aware(naive, timezone.get_current_timezone())
    except Exception:
        return None


def _to_int(value):
    try:
        return int(value or 0)
    except Exception:
        return None


def get_media_backup_status() -> MediaBackupStatus:
    """
    Report the latest media/uploads backup recorded by the external backup script.

    This function only reads the manifest. It does not execute backups.
    """
    if not MANIFEST_PATH.exists():
        return MediaBackupStatus(
            configured=False,
            error="Media backup manifest not found.",
        )

    try:
        lines = [
            line.rstrip("\n")
            for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        if len(lines) < 2:
            return MediaBackupStatus(
                configured=True,
                error="Media backup manifest has no backup entries.",
            )

        header = lines[0].split("\t")
        latest = lines[-1].split("\t")
        row = dict(zip(header, latest))

        timestamp = row.get("timestamp")
        latest_dt = _parse_timestamp(timestamp or "")
        age_hours = None

        if latest_dt:
            age_hours = round((timezone.now() - latest_dt).total_seconds() / 3600, 2)

        archive = row.get("archive") or None

        file_error = None
        if archive and not Path(archive).exists():
            file_error = "Latest media backup archive listed in manifest does not exist."

        return MediaBackupStatus(
            configured=True,
            latest_status=row.get("status"),
            latest_timestamp=timestamp,
            latest_archive=archive,
            latest_archive_bytes=_to_int(row.get("archive_bytes")),
            latest_source_file_count=_to_int(row.get("source_file_count")),
            latest_source_bytes=_to_int(row.get("source_bytes")),
            latest_sha256=row.get("sha256"),
            latest_age_hours=age_hours,
            error=file_error,
        )

    except Exception as exc:
        return MediaBackupStatus(
            configured=True,
            error=str(exc),
        )
