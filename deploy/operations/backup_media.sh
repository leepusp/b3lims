#!/usr/bin/env bash
set -euo pipefail

MEDIA_ROOT="/home/public/apps/biobank/storage/data"
BACKUP_ROOT="/home/public/apps/biobank/storage/backups/media"
DAILY_DIR="$BACKUP_ROOT/daily"
MANIFEST_DIR="$BACKUP_ROOT/manifests"
LOG_DIR="/home/public/apps/biobank/storage/logs/backups"

KEEP_DAYS="${KEEP_DAYS:-30}"

TS="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="$DAILY_DIR/biobank_media_${TS}.tar.gz"
TMP_ARCHIVE="${ARCHIVE}.tmp"
SHA_FILE="${ARCHIVE}.sha256"
MANIFEST="$MANIFEST_DIR/media_backups.tsv"
LOG_FILE="$LOG_DIR/media_backup_${TS}.log"

mkdir -p "$DAILY_DIR" "$MANIFEST_DIR" "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "timestamp=$TS"
echo "media_root=$MEDIA_ROOT"
echo "archive=$ARCHIVE"
echo "keep_days=$KEEP_DAYS"

if [ ! -d "$MEDIA_ROOT" ]; then
  echo "ERROR: MEDIA_ROOT does not exist: $MEDIA_ROOT"
  exit 1
fi

FILE_COUNT="$(find "$MEDIA_ROOT" -type f | wc -l)"
TOTAL_BYTES="$(find "$MEDIA_ROOT" -type f -printf '%s\n' | awk '{s+=$1} END {print s+0}')"

echo "file_count=$FILE_COUNT"
echo "source_bytes=$TOTAL_BYTES"

tar \
  --create \
  --gzip \
  --file "$TMP_ARCHIVE" \
  --directory "$MEDIA_ROOT" \
  .

mv "$TMP_ARCHIVE" "$ARCHIVE"

sha256sum "$ARCHIVE" > "$SHA_FILE"

ARCHIVE_BYTES="$(stat -c '%s' "$ARCHIVE")"
SHA256="$(awk '{print $1}' "$SHA_FILE")"

echo "archive_bytes=$ARCHIVE_BYTES"
echo "sha256=$SHA256"

echo "=== Validate archive listing ==="
tar -tzf "$ARCHIVE" >/dev/null

if [ ! -s "$MANIFEST" ]; then
  printf "timestamp\tmedia_root\tarchive\tarchive_bytes\tsource_file_count\tsource_bytes\tsha256\tstatus\n" > "$MANIFEST"
fi

printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\tok\n" \
  "$TS" \
  "$MEDIA_ROOT" \
  "$ARCHIVE" \
  "$ARCHIVE_BYTES" \
  "$FILE_COUNT" \
  "$TOTAL_BYTES" \
  "$SHA256" \
  >> "$MANIFEST"

echo "=== Retention cleanup ==="
find "$DAILY_DIR" -type f -name 'biobank_media_*.tar.gz' -mtime +"$KEEP_DAYS" -print -delete
find "$DAILY_DIR" -type f -name 'biobank_media_*.tar.gz.sha256' -mtime +"$KEEP_DAYS" -print -delete
find "$LOG_DIR" -type f -name 'media_backup_*.log' -mtime +"$KEEP_DAYS" -print -delete

echo "OK: media backup completed"
