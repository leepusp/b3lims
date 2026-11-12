#!/bin/sh
# First start: create the installation from environment variables; later starts only run it.
set -e

ROOT="${BIOBANK_LOCAL_ROOT:-/data}"

if [ ! -f "$ROOT/config.env" ]; then
    if [ -z "$BIOBANK_ADMIN_PASSWORD" ]; then
        echo "Set BIOBANK_ADMIN_PASSWORD (at least 8 characters) for the first start." >&2
        exit 2
    fi

    biobank-local --root "$ROOT" setup --non-interactive \
        --admin-user "${BIOBANK_ADMIN_USER:-admin}" \
        --admin-email "${BIOBANK_ADMIN_EMAIL:-}" \
        --host 0.0.0.0 \
        --allowed-hosts "${BIOBANK_ALLOWED_HOSTS:-localhost,127.0.0.1}" \
        --time-zone "${BIOBANK_TIME_ZONE:-UTC}" \
        ${BIOBANK_DATABASE_URL:+--database-url "$BIOBANK_DATABASE_URL"}
else
    # A newer image: bring the existing database up to date (never touches accounts).
    biobank-local --root "$ROOT" migrate
fi

exec biobank-local --root "$ROOT" run --host 0.0.0.0 --port 8000
