#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

APP_ROOT="/home/public/apps/biobank"
REPO_ROOT="/home/ladmin/git/biobank"
PYTHON_BIN="/home/public/conda/envs/biobank/bin/python"
ENV_FILE="/home/public/apps/biobank/storage/secrets/biobank_db.env"

PG_DUMP="/usr/pgsql-18/bin/pg_dump"
PG_RESTORE="/usr/pgsql-18/bin/pg_restore"

BACKUP_ROOT="${APP_ROOT}/storage/backups/postgresql"
DAILY_DIR="${BACKUP_ROOT}/daily"
MANIFEST_DIR="${BACKUP_ROOT}/manifests"
LOG_DIR="${APP_ROOT}/storage/logs/backups"

KEEP_DAYS="${KEEP_DAYS:-14}"

NOW="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/backup_postgresql_${NOW}.log"
DUMP_FILE="${DAILY_DIR}/biobank_${NOW}.dump"
SHA_FILE="${DUMP_FILE}.sha256"
MANIFEST_FILE="${MANIFEST_DIR}/postgresql_backups.tsv"

mkdir -p "$DAILY_DIR" "$MANIFEST_DIR" "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Biobank PostgreSQL backup ==="
echo "timestamp=$NOW"
echo "host=$(hostname)"
echo "repo=$REPO_ROOT"
echo "dump=$DUMP_FILE"

cd "$REPO_ROOT"

set -a
source "$ENV_FILE"
set +a

eval "$("$PYTHON_BIN" <<'PYCONF'
import os
import shlex

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "biobank.settings")

import django
django.setup()

from django.conf import settings

db = settings.DATABASES["default"]

def emit(key, value):
    print(f"{key}={shlex.quote(str(value or ''))}")

emit("DB_NAME", db.get("NAME"))
emit("DB_USER", db.get("USER"))
emit("DB_HOST", db.get("HOST") or "127.0.0.1")
emit("DB_PORT", db.get("PORT") or "5432")
emit("DB_PASSWORD", db.get("PASSWORD"))
emit("DB_ENGINE", db.get("ENGINE"))
PYCONF
)"

if [[ "$DB_ENGINE" != *"postgresql"* ]]; then
    echo "ERROR: Django default database is not PostgreSQL: $DB_ENGINE"
    exit 1
fi

PGPASSFILE="$(mktemp)"
trap 'rm -f "$PGPASSFILE"' EXIT
chmod 600 "$PGPASSFILE"
printf '%s:%s:%s:%s:%s\n' "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASSWORD" > "$PGPASSFILE"
export PGPASSFILE

echo "database=$DB_NAME"
echo "db_user=$DB_USER"
echo "db_host=$DB_HOST"
echo "db_port=$DB_PORT"

env -i \
    PATH="/usr/pgsql-18/bin:/usr/bin:/bin" \
    HOME="$HOME" \
    LANG="${LANG:-C.UTF-8}" \
    PGPASSFILE="$PGPASSFILE" \
    "$PG_DUMP" \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --format=custom \
    --no-owner \
    --no-acl \
    --file="$DUMP_FILE"

env -i \
    PATH="/usr/pgsql-18/bin:/usr/bin:/bin" \
    HOME="$HOME" \
    LANG="${LANG:-C.UTF-8}" \
    PGPASSFILE="$PGPASSFILE" \
    "$PG_RESTORE" --list "$DUMP_FILE" >/dev/null

sha256sum "$DUMP_FILE" > "$SHA_FILE"

BYTES="$(stat -c '%s' "$DUMP_FILE")"
SHA256="$(awk '{print $1}' "$SHA_FILE")"

if [[ ! -f "$MANIFEST_FILE" ]]; then
    printf 'timestamp\tdatabase\thost\tport\tfile\tbytes\tsha256\tstatus\n' > "$MANIFEST_FILE"
fi

printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$NOW" "$DB_NAME" "$DB_HOST" "$DB_PORT" "$DUMP_FILE" "$BYTES" "$SHA256" "ok" \
    >> "$MANIFEST_FILE"

find "$DAILY_DIR" -type f -name 'biobank_*.dump' -mtime +"$KEEP_DAYS" -delete
find "$DAILY_DIR" -type f -name 'biobank_*.dump.sha256' -mtime +"$KEEP_DAYS" -delete
find "$LOG_DIR" -type f -name 'backup_postgresql_*.log' -mtime +"$KEEP_DAYS" -delete

echo "OK: PostgreSQL backup completed."
echo "file=$DUMP_FILE"
echo "bytes=$BYTES"
echo "sha256=$SHA256"
