from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.utils import timezone


MANIFEST_PATH = Path(
    "/home/public/apps/biobank/storage/backups/postgresql/manifests/postgresql_backups.tsv"
)


@dataclass
class PostgreSQLBackupStatus:
    configured: bool
    latest_status: str | None = None
    latest_timestamp: str | None = None
    latest_file: str | None = None
    latest_bytes: int | None = None
    latest_sha256: str | None = None
    latest_age_hours: float | None = None
    error: str | None = None


def _parse_timestamp(value: str):
    try:
        naive = datetime.strptime(value, "%Y%m%d_%H%M%S")
        return timezone.make_aware(naive, timezone.get_current_timezone())
    except Exception:
        return None


def get_postgresql_backup_status() -> PostgreSQLBackupStatus:
    """
    Report the latest PostgreSQL backup recorded by the external backup script.

    This function only reads the manifest. It does not execute backups.
    """
    if not MANIFEST_PATH.exists():
        return PostgreSQLBackupStatus(
            configured=False,
            error="Backup manifest not found.",
        )

    try:
        lines = [
            line.rstrip("\n")
            for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        if len(lines) < 2:
            return PostgreSQLBackupStatus(
                configured=True,
                error="Backup manifest has no backup entries.",
            )

        header = lines[0].split("\t")
        latest = lines[-1].split("\t")
        row = dict(zip(header, latest))

        timestamp = row.get("timestamp")
        latest_dt = _parse_timestamp(timestamp or "")
        age_hours = None

        if latest_dt:
            age_hours = round((timezone.now() - latest_dt).total_seconds() / 3600, 2)

        latest_file = row.get("file") or None

        try:
            latest_bytes = int(row.get("bytes") or 0)
        except Exception:
            latest_bytes = None

        file_error = None
        if latest_file and not Path(latest_file).exists():
            file_error = "Latest backup file listed in manifest does not exist."

        return PostgreSQLBackupStatus(
            configured=True,
            latest_status=row.get("status"),
            latest_timestamp=timestamp,
            latest_file=latest_file,
            latest_bytes=latest_bytes,
            latest_sha256=row.get("sha256"),
            latest_age_hours=age_hours,
            error=file_error,
        )

    except Exception as exc:
        return PostgreSQLBackupStatus(
            configured=True,
            error=str(exc),
        )
