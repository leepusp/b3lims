# Biobank media/uploads backup

Biobank stores uploaded files outside PostgreSQL under MEDIA_ROOT.

Current MEDIA_ROOT:

    /home/public/apps/biobank/storage/data

This directory contains sample files, notebook attachments, shipment documents,
signed transport documents and sample import files.

PostgreSQL backups do not include these files. They are backed up separately.

## Backup script

    /home/public/apps/biobank/scripts/backup_media.sh

## Output

Daily archives:

    /home/public/apps/biobank/storage/backups/media/daily/biobank_media_YYYYMMDD_HHMMSS.tar.gz
    /home/public/apps/biobank/storage/backups/media/daily/biobank_media_YYYYMMDD_HHMMSS.tar.gz.sha256

Manifest:

    /home/public/apps/biobank/storage/backups/media/manifests/media_backups.tsv

Logs:

    /home/public/apps/biobank/storage/logs/backups/media_backup_YYYYMMDD_HHMMSS.log

## Schedule

The media backup is scheduled in the ladmin crontab:

    50 3 * * * /home/public/apps/biobank/scripts/backup_media.sh >/dev/null 2>&1

The PostgreSQL backup runs earlier at 03:20.

## Retention

The script keeps media backups for 30 days by default.

Retention can be changed by setting:

    KEEP_DAYS=<days>

## Manual validation

    LATEST_MEDIA="$(ls -t /home/public/apps/biobank/storage/backups/media/daily/biobank_media_*.tar.gz | head -1)"
    LATEST_SHA="${LATEST_MEDIA}.sha256"

    sha256sum -c "$LATEST_SHA"
    tar -tzf "$LATEST_MEDIA" | sed -n '1,40p'

## Restore strategy

A restore should be tested into a temporary directory before restoring into
production MEDIA_ROOT.

Example:

    mkdir -p /tmp/biobank_media_restore_test
    tar -xzf biobank_media_YYYYMMDD_HHMMSS.tar.gz -C /tmp/biobank_media_restore_test

Production restore must be performed only after selecting the correct database
backup and matching media archive from a compatible point in time.
