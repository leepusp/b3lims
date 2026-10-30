#!/usr/bin/env bash
set -euo pipefail
umask 077

# B3_CUTOVER_LOCK_BEGIN
# Shared with the root-owned C4-G cutover executor.
# Hold this descriptor for the entire script execution.
B3_RELEASE_LOCK="/run/lock/b3lims-deploy-shared.lock"
B3_RELEASE_LOCK_EXPECTED_UID=0
B3_RELEASE_LOCK_EXPECTED_GID="$(id -g ladmin)"

if test -L "$B3_RELEASE_LOCK" ||
   test ! -f "$B3_RELEASE_LOCK"
then
    echo "ERROR: B3 release lock unavailable." >&2
    exit 73
fi

B3_RELEASE_LOCK_META="$(
    stat -c '%u:%g:%a:%h' "$B3_RELEASE_LOCK"
)"

if test "$B3_RELEASE_LOCK_META" != \
   "${B3_RELEASE_LOCK_EXPECTED_UID}:${B3_RELEASE_LOCK_EXPECTED_GID}:660:1"
then
    echo "ERROR: B3 release lock metadata invalid." >&2
    exit 73
fi

if ! exec {B3_RELEASE_LOCK_FD}<>"$B3_RELEASE_LOCK"
then
    echo "ERROR: B3 release lock cannot be opened." >&2
    exit 73
fi

if ! flock -n -x "$B3_RELEASE_LOCK_FD"
then
    echo "ERROR: B3 release operation already active." >&2
    exit 75
fi
# B3_CUTOVER_LOCK_END

# Resolve the Git worktree containing this versioned script.
# During development this is the feature worktree; after
# integration this is the canonical main checkout.
SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
    pwd -P
)"

REPO="$(
    git -C "$SCRIPT_DIR" rev-parse --show-toplevel
)"
APP="/home/public/apps/biobank"
PY="/home/public/conda/envs/biobank/bin/python"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    echo "Usage: $0 --preflight|--stage FULL_GIT_COMMIT"
    echo "This version cannot activate production."
}

if test "$#" -ne 2; then
    usage >&2
    exit 2
fi

MODE="$1"
TARGET="$2"

case "$MODE" in
    --preflight|--stage) ;;
    *)
        usage >&2
        exit 2
        ;;
esac

[[ "$TARGET" =~ ^[0-9a-f]{40}$ ]] ||
    fail "A full 40-character Git commit is required."

test "$(id -un)" = "ladmin" ||
    fail "Preparation must run as ladmin."

test -x "$PY" || fail "Python environment missing."

test "$(git -C "$REPO" rev-parse HEAD)" = "$TARGET" ||
    fail "Canonical repository HEAD differs from target."

test -z "$(git -C "$REPO" status --porcelain=v1)" ||
    fail "Canonical repository is dirty."

git -C "$REPO" cat-file -e "${TARGET}^{commit}" ||
    fail "Target commit is unavailable."

test -L "$APP/current" ||
    fail "Application current link missing."

test -L "$APP/static-current" ||
    fail "Static current link missing."

CURRENT="$(readlink -f "$APP/current")"
STATIC="$(readlink -f "$APP/static-current")"

case "$CURRENT" in
    "$APP/releases/"*) ;;
    *) fail "Application current is outside release root." ;;
esac

case "$STATIC" in
    "$APP/static-releases/"*) ;;
    *) fail "Static current is outside static release root." ;;
esac

ACTIVE="$(basename "$CURRENT")"
STATIC_ID="$(basename "$STATIC")"

# Application-only deployments may retain an older,
# immutable static release.
#
# Accept different identifiers only after proving:
# - Git ancestry;
# - no static source differences;
# - official HTTPS asset integrity.
#
# No direct filesystem access to biobank-proxy is needed.

if test "$ACTIVE" != "$STATIC_ID"; then

    git -C "$REPO" cat-file -e         "${STATIC_ID}^{commit}" ||
        fail "Static release is not a Git commit."

    git -C "$REPO" merge-base --is-ancestor         "$STATIC_ID" "$ACTIVE" ||
        fail "Static release is not an ancestor."

    git -C "$REPO" diff --quiet         "$STATIC_ID" "$ACTIVE" --         core/static static biobank/static ||
        fail "Static source differs between releases."

    STATIC_URL="https://davinci.icb.usp.br/b3lims/static/internal/storage"

    for FILE in         storage_v814.js         storage_contextual_v7.js         storage_relationship_v89.js
    do
        SOURCE="core/static/internal/storage/$FILE"

        EXPECTED_SHA="$(
            git -C "$REPO" show "${STATIC_ID}:$SOURCE" |
            sha256sum |
            awk '{print $1}'
        )" ||
            fail "Unable to hash Git asset: $FILE"

        LIVE_SHA="$(
            curl                 --fail                 --silent                 --show-error                 --proto '=https'                 --tlsv1.2                 --connect-timeout 5                 --max-time 30                 --header 'Cache-Control: no-cache'                 "$STATIC_URL/$FILE?integrity=$STATIC_ID" |
            sha256sum |
            awk '{print $1}'
        )" ||
            fail "Unable to verify HTTPS asset: $FILE"

        test -n "$EXPECTED_SHA" ||
            fail "Empty Git checksum: $FILE"

        test "$EXPECTED_SHA" = "$LIVE_SHA" ||
            fail "Live static checksum mismatch: $FILE"

        echo "verified_live_static_asset=$FILE"
    done
fi

test -d "$CURRENT" || fail "Active code release missing."
test -d "$STATIC" || fail "Active static release missing."

test "$ACTIVE" != "$TARGET" ||
    fail "Target is already active."

git -C "$REPO" cat-file -e "${ACTIVE}^{commit}" ||
    fail "Active release is not a known Git commit."

git -C "$REPO" merge-base --is-ancestor \
    "$ACTIVE" "$TARGET" ||
    fail "Target does not descend from active release."

test ! -e "$APP/releases/$TARGET" ||
    fail "Target application release already exists."

test ! -e "$APP/static-releases/$TARGET" ||
    fail "Target static release already exists."

systemctl is-active --quiet biobank ||
    fail "Biobank service is not active."

systemctl is-active --quiet httpd ||
    fail "Apache is not active."

CHANGED="$(
    git -C "$REPO" diff \
        --name-only "$ACTIVE" "$TARGET"
)"

if grep -Eq '(^|/)migrations/.*\.py$' <<< "$CHANGED"; then
    fail "Schema migrations require a separate deployment review."
fi

echo "=============================================="
echo "COORDINATED RELEASE PREPARATION"
echo "=============================================="
echo "target=$TARGET"
echo "active=$ACTIVE"
echo "current=$CURRENT"
echo "static_current=$STATIC"
echo "static_base=$STATIC_ID"
echo "migration_delta=NONE"
echo "production_modified=NO"
echo "preflight=PASS"

if test "$MODE" = "--preflight"; then
    exit 0
fi

echo
echo "=== BUILD ISOLATED CANDIDATE ==="

BUILD="$(mktemp -d /tmp/b3lims-release-stage.XXXXXXXX)"

trap '
    rc=$?
    if test "$rc" -ne 0; then
        rm -rf -- "$BUILD"
    fi
' EXIT

mkdir -m 0700 \
    "$BUILD/app" \
    "$BUILD/private-media"

git -C "$REPO" archive \
    --format=tar "$TARGET" |
    tar -xf - -C "$BUILD/app"

test -f "$BUILD/app/manage.py" ||
    fail "Staged application is incomplete."

cd "$BUILD/app"

echo
echo "=== VERIFY ISOLATED SETTINGS ==="

env -u DATABASE_URL \
    DJANGO_SETTINGS_MODULE=biobank.settings \
    BIOBANK_MEDIA_ROOT="$BUILD/private-media" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" - <<'PY'
from pathlib import Path
from django.conf import settings

base = Path.cwd().resolve()
db = settings.DATABASES["default"]

assert db["ENGINE"] == "django.db.backends.sqlite3"
assert Path(settings.STATIC_ROOT).resolve() == (
    base / "staticfiles"
)
assert Path(settings.MEDIA_ROOT).resolve() == (
    base.parent / "private-media"
)

print("DATABASE=ISOLATED_SQLITE")
print("STATIC_ROOT=ISOLATED")
print("MEDIA_ROOT=ISOLATED")
PY

echo
echo "=== DJANGO SYSTEM CHECK ==="

env -u DATABASE_URL \
    DJANGO_SETTINGS_MODULE=biobank.settings \
    BIOBANK_MEDIA_ROOT="$BUILD/private-media" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" manage.py check

echo
echo "=== BUILD STATIC ASSETS ==="

env -u DATABASE_URL \
    DJANGO_SETTINGS_MODULE=biobank.settings \
    BIOBANK_MEDIA_ROOT="$BUILD/private-media" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" manage.py collectstatic \
        --noinput --verbosity=1

echo
echo "=== VERIFY STORAGE JAVASCRIPT ==="

for file in \
    storage_contextual_v7.js \
    storage_relationship_v89.js \
    storage_v814.js
do
    SRC="core/static/internal/storage/$file"
    DST="staticfiles/internal/storage/$file"

    test -s "$SRC" || fail "Source missing: $file"
    test -s "$DST" || fail "Collected asset missing: $file"

    cmp -s "$SRC" "$DST" ||
        fail "Collected asset differs from Git source: $file"

    echo "$file=PASS"
done

echo
echo "=== VERIFY STAGED JAVASCRIPT TESTS ==="

node --check \
    core/static/internal/storage/storage_relationship_v89.js

node --check \
    core/static/internal/storage/storage_v814.js

for test_file in \
    core/tests/js/test_storage_visual_tree_v810.cjs \
    core/tests/js/test_storage_visual_dom_v810.cjs \
    core/tests/js/test_storage_movement_overlay_v810.cjs \
    core/tests/js/test_storage_relationship_sync_v89c.cjs
do
    node "$test_file"
done

echo
echo "=== BUILD MANIFEST ==="

{
    echo "target=$TARGET"
    echo "base=$ACTIVE"
    echo "static_base=$STATIC_ID"
    echo "status=offline_candidate"
    echo "production_modified=NO"
    echo "migration_delta=NONE"
    echo "database=isolated_sqlite"
} > "$BUILD/manifest.txt"

find staticfiles -type f -print0 |
    sort -z |
    xargs -0 -r sha256sum \
    > "$BUILD/static-sha256.txt"

echo
echo "=== VERIFY LIVE LINKS UNCHANGED ==="

test "$(readlink -f "$APP/current")" = "$CURRENT" ||
    fail "Application link changed during staging."

test "$(readlink -f "$APP/static-current")" = "$STATIC" ||
    fail "Static link changed during staging."

echo
echo "=============================================="
echo "V810_COORDINATED_STAGE=PASS"
echo "BUILD_DIRECTORY=$BUILD"
echo "PRODUCTION_MODIFIED=NO"
echo "=============================================="
