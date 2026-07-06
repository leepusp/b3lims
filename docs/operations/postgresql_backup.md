# Biobank PostgreSQL backup

Biobank uses PostgreSQL as the authoritative database backend.

The production backup is a PostgreSQL logical backup generated with pg_dump
in custom format. The legacy Django dumpdata export workflow was removed and
must not be treated as a production backup.

## Runtime database

Current Django database backend:

- Engine: django.db.backends.postgresql
- Database: biobank
- Host: 127.0.0.1
- Port: 5432
- PostgreSQL major version: 18

Credentials are loaded from:

    /home/public/apps/biobank/storage/secrets/biobank_db.env

## Backup script

The backup script is located at:

    /home/public/apps/biobank/scripts/backup_postgresql.sh

It generates:

    /home/public/apps/biobank/storage/backups/postgresql/daily/biobank_YYYYMMDD_HHMMSS.dump
    /home/public/apps/biobank/storage/backups/postgresql/daily/biobank_YYYYMMDD_HHMMSS.dump.sha256

The manifest is located at:

    /home/public/apps/biobank/storage/backups/postgresql/manifests/postgresql_backups.tsv

## Schedule

The backup is scheduled in the ladmin crontab:

    20 3 * * * /home/public/apps/biobank/scripts/backup_postgresql.sh >/dev/null 2>&1

## Retention

The script currently keeps daily backups for 14 days by default.

The retention can be changed by setting:

    KEEP_DAYS=<days>

## Manual run

    /home/public/apps/biobank/scripts/backup_postgresql.sh

## Verify latest backup

    LATEST_DUMP="$(ls -t /home/public/apps/biobank/storage/backups/postgresql/daily/biobank_*.dump | head -1)"
    LATEST_SHA="${LATEST_DUMP}.sha256"
    sha256sum -c "$LATEST_SHA"
    /usr/pgsql-18/bin/pg_restore --list "$LATEST_DUMP" | sed -n '1,30p'

## Restore strategy

A restore should be tested into a temporary PostgreSQL database before being
used in production.

Example outline:

    createdb biobank_restore_test
    pg_restore --clean --if-exists --no-owner --no-acl --dbname=biobank_restore_test biobank_YYYYMMDD_HHMMSS.dump

Production restore must be done only after stopping write traffic to the
application and confirming the selected backup checksum.

## Current status

Validated manually:

- pg_dump custom format: OK
- sha256 verification: OK
- pg_restore --list: OK
- cron-like minimal environment execution: OK
- manifest generation: OK
