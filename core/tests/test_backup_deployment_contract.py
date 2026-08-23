from pathlib import Path
import stat

from django.conf import settings
from django.test import SimpleTestCase


class BackupDeploymentContractTests(SimpleTestCase):
    @staticmethod
    def _path(relative):
        return Path(settings.BASE_DIR) / relative

    @classmethod
    def _source(cls, relative):
        return cls._path(relative).read_text()

    def test_backup_sources_are_versioned_and_executable(self):
        for relative in (
            "deploy/operations/backup_postgresql.sh",
            "deploy/operations/backup_media.sh",
        ):
            path = self._path(relative)

            self.assertTrue(path.is_file())
            self.assertTrue(
                path.stat().st_mode & stat.S_IXUSR
            )

    def test_postgresql_backup_contract(self):
        source = self._source(
            "deploy/operations/backup_postgresql.sh"
        )

        for marker in (
            'ENV_FILE="/home/public/apps/biobank/storage/secrets/biobank_db.env"',
            'PG_DUMP="/usr/pgsql-18/bin/pg_dump"',
            'PG_RESTORE="/usr/pgsql-18/bin/pg_restore"',
            '--format=custom',
            '--no-owner',
            '--no-acl',
            '"$PG_RESTORE" --list "$DUMP_FILE"',
            'sha256sum "$DUMP_FILE"',
            'KEEP_DAYS="${KEEP_DAYS:-14}"',
            'postgresql_backups.tsv',
        ):
            self.assertIn(marker, source)

        self.assertNotIn(
            "BIOBANK_DB_PASSWORD=",
            source,
        )

    def test_media_backup_contract(self):
        source = self._source(
            "deploy/operations/backup_media.sh"
        )

        for marker in (
            'MEDIA_ROOT="/home/public/apps/biobank/storage/data"',
            'TMP_ARCHIVE="${ARCHIVE}.tmp"',
            'sha256sum "$ARCHIVE"',
            'tar -tzf "$ARCHIVE"',
            'KEEP_DAYS="${KEEP_DAYS:-30}"',
            'media_backups.tsv',
        ):
            self.assertIn(marker, source)

    def test_canonical_cron_schedule(self):
        source = self._source(
            "deploy/cron/ladmin-biobank-backups"
        )

        entries = [
            line
            for line in source.splitlines()
            if line and not line.startswith("#")
        ]

        self.assertEqual(
            entries,
            [
                (
                    "20 3 * * * "
                    "/home/public/apps/biobank/scripts/"
                    "backup_postgresql.sh >/dev/null 2>&1"
                ),
                (
                    "50 3 * * * "
                    "/home/public/apps/biobank/scripts/"
                    "backup_media.sh >/dev/null 2>&1"
                ),
            ],
        )

    def test_documented_secret_and_source_contract(self):
        postgresql = self._source(
            "docs/operations/postgresql_backup.md"
        )
        media = self._source(
            "docs/operations/media_backup.md"
        )

        for marker in (
            "deploy/operations/backup_postgresql.sh",
            "deploy/cron/ladmin-biobank-backups",
            "`root:ladmin`, mode `2750`",
            "`root:ladmin`, mode `0640`",
            "Credential values must never be committed",
        ):
            self.assertIn(marker, postgresql)

        for marker in (
            "deploy/operations/backup_media.sh",
            "deploy/cron/ladmin-biobank-backups",
        ):
            self.assertIn(marker, media)
