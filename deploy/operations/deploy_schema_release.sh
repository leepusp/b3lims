#!/usr/bin/env bash
#
# B3 LIMS schema + static release.
#
# Use this when the generic application deploy refuses a target because
# it adds migrations or changes static assets. Same release model as
# deploy_application_release.sh and deploy_coordinated_release.sh:
#
#   releases/<commit>          immutable code release (git archive)
#   static-releases/<commit>   immutable collectstatic output
#   current, static-current    links switched together
#
# Usage (as root):
#   deploy_schema_release.sh --preflight FULL_GIT_COMMIT
#   deploy_schema_release.sh FULL_GIT_COMMIT PLAN_SHA256
#
# The preflight prints the exact migration plan and PLAN_SHA256. The
# deploy refuses to run unless the plan is unchanged, so what was
# reviewed is what gets applied.
#
# Schema rules:
#   - the plan may contain only migration files ADDED between the live
#     release and the target; edited or deleted migrations are refused;
#   - a PostgreSQL backup is taken before anything is changed;
#   - migrations are applied before the code cutover, so they must be
#     additive (the live code keeps running against the new schema);
#   - if the cutover fails, code and static links are rolled back; the
#     schema is NOT reversed automatically (the manifest says how).

set -Eeuo pipefail
umask 0027

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

REPO="/home/ladmin/git/biobank"

APP_ROOT="/home/public/apps/biobank"
RELEASE_ROOT="$APP_ROOT/releases"
STATIC_RELEASE_ROOT="$APP_ROOT/static-releases"
CURRENT_LINK="$APP_ROOT/current"
STATIC_LINK="$APP_ROOT/static-current"

PY="/home/public/conda/envs/biobank/bin/python"
ENV_FILE="/etc/biobank/runtime.env"
BACKUP_SCRIPT="$APP_ROOT/scripts/backup_postgresql.sh"

SERVICE="biobank"

BASE_URL="https://davinci.icb.usp.br/b3lims"

MANIFEST_ROOT="$APP_ROOT/storage/manifests/deployment"

MODE="deploy"

if test "${1:-}" = "--preflight"
then
    MODE="preflight"
    shift
fi

usage() {
    printf '%s\n' \
        "Usage:" \
        "  $0 --preflight FULL_GIT_COMMIT" \
        "  $0 FULL_GIT_COMMIT PLAN_SHA256" \
        >&2
}

if test "$MODE" = "preflight"
then
    test "$#" -eq 1 || { usage; exit 2; }
    TARGET_COMMIT="$1"
    APPROVED_PLAN_SHA=""
else
    test "$#" -eq 2 || { usage; exit 2; }
    TARGET_COMMIT="$1"
    APPROVED_PLAN_SHA="$2"

    [[ "$APPROVED_PLAN_SHA" =~ ^[0-9a-f]{64}$ ]] || {
        echo "ERROR: PLAN_SHA256 must be the 64-character value printed by --preflight." >&2
        exit 2
    }
fi

[[ "$TARGET_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
    echo "ERROR: target must be a full 40-character Git commit." >&2
    exit 2
}

test "${EUID}" -eq 0 || {
    echo "ERROR: run schema deployment as root." >&2
    exit 2
}


repo_git() {
    runuser \
        -u ladmin \
        -- \
        git -C "$REPO" "$@"
}


STAMP="$(
    date -u '+%Y%m%dT%H%M%SZ'
)"

TARGET_RELEASE="$RELEASE_ROOT/$TARGET_COMMIT"
STAGE_RELEASE="$RELEASE_ROOT/.${TARGET_COMMIT}.${STAMP}.staging"

TARGET_STATIC="$STATIC_RELEASE_ROOT/$TARGET_COMMIT"
STAGE_STATIC="$STATIC_RELEASE_ROOT/.${TARGET_COMMIT}.${STAMP}.staging"

WORK_DIR="$APP_ROOT/.schema-release.${TARGET_COMMIT}.${STAMP}"

MANIFEST="$MANIFEST_ROOT/schema-${TARGET_COMMIT}-${STAMP}"

CURRENT_RELEASE=""
CURRENT_RELEASE_ID=""
OLD_CURRENT_LINK=""
STATIC_BEFORE=""
OLD_STATIC_LINK=""
OLD_PID=""
PLAN_SHA=""
BACKUP_FILE=""

TARGET_RELEASE_CREATED=0
TARGET_STATIC_CREATED=0
SCHEMA_APPLIED=0
MUTATED=0
ROLLBACK_DONE=0
ABORTING=0
MANIFEST_CREATED=0


record_result() {
    test "$MANIFEST_CREATED" -eq 1 ||
        return 0

    printf '%s\n' "$@" \
        >> "$MANIFEST/result.txt" \
        2>/dev/null \
        || true
}


cleanup_work_dirs() {
    set +e

    rm -rf -- \
        "$WORK_DIR" \
        "$STAGE_RELEASE" \
        "$STAGE_STATIC"
}


runtime_cwd() {
    local pid=""

    pid="$(
        systemctl show -p MainPID --value "$SERVICE" 2>/dev/null
    )"

    if test -n "$pid" && test "$pid" != "0"
    then
        readlink -f "/proc/$pid/cwd" 2>/dev/null || true
    fi
}


swap_link() {
    local link="$1"
    local destination="$2"
    local temporary

    temporary="$APP_ROOT/.$(basename "$link").switch.${STAMP}"

    rm -f -- "$temporary"
    ln -s "$destination" "$temporary"
    mv -Tf "$temporary" "$link"
}


rollback() {
    local rc="$1"
    local rollback_safe=1
    local restored_current=""
    local restored_static=""
    local rollback_cwd=""

    set +e

    if test "$ROLLBACK_DONE" -eq 1
    then
        return
    fi

    ROLLBACK_DONE=1

    if test "$MUTATED" -ne 1
    then
        return
    fi

    record_result \
        "status=rollback" \
        "exit_code=$rc" \
        "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    systemctl stop "$SERVICE" \
        >/dev/null 2>&1 \
        || rollback_safe=0

    if test -n "$OLD_CURRENT_LINK" &&
       test -n "$OLD_STATIC_LINK"
    then
        swap_link "$CURRENT_LINK" "$OLD_CURRENT_LINK" ||
            rollback_safe=0
        swap_link "$STATIC_LINK" "$OLD_STATIC_LINK" ||
            rollback_safe=0
    else
        rollback_safe=0
    fi

    restored_current="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
    restored_static="$(readlink -f "$STATIC_LINK" 2>/dev/null || true)"

    test "$restored_current" = "$CURRENT_RELEASE" ||
        rollback_safe=0

    test "$restored_static" = "$STATIC_BEFORE" ||
        rollback_safe=0

    if test "$rollback_safe" -eq 1
    then
        systemctl restart "$SERVICE" \
            >/dev/null 2>&1 \
            || rollback_safe=0
    fi

    if test "$rollback_safe" -eq 1
    then
        sleep 0.5
        rollback_cwd="$(runtime_cwd)"

        test "$rollback_cwd" = "$CURRENT_RELEASE" ||
            rollback_safe=0
    fi

    if test "$rollback_safe" -eq 1
    then
        record_result \
            "rollback_contract=RESTORED" \
            "rollback_current=$restored_current" \
            "rollback_static=$restored_static" \
            "rollback_cwd=$rollback_cwd"

        echo "Rollback: previous code and static releases restored." >&2
    else
        record_result \
            "rollback_contract=INCOMPLETE_FAIL_CLOSED"

        echo "ERROR: rollback could not be fully proven; fail closed." >&2
    fi
}


cleanup_failed_release() {
    local current_resolved=""
    local static_resolved=""
    local cwd=""

    set +e

    cleanup_work_dirs

    current_resolved="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
    static_resolved="$(readlink -f "$STATIC_LINK" 2>/dev/null || true)"
    cwd="$(runtime_cwd)"

    if test "$TARGET_RELEASE_CREATED" -eq 1 &&
       test -e "$TARGET_RELEASE"
    then
        if test "$current_resolved" != "$TARGET_RELEASE" &&
           test "$cwd" != "$TARGET_RELEASE"
        then
            rm -rf -- "$TARGET_RELEASE"
        else
            record_result "warning=failed_target_release_retained"
        fi
    fi

    if test "$TARGET_STATIC_CREATED" -eq 1 &&
       test -e "$TARGET_STATIC"
    then
        if test "$static_resolved" != "$TARGET_STATIC"
        then
            rm -rf -- "$TARGET_STATIC"
        else
            record_result "warning=failed_target_static_retained"
        fi
    fi
}


report_schema_state() {
    if test "$SCHEMA_APPLIED" -eq 1
    then
        record_result \
            "schema_applied=YES" \
            "schema_reverse_hint=see migration plan in $MANIFEST/migration-plan.txt" \
            "backup_file=$BACKUP_FILE"

        printf '%s\n' \
            "NOTE: migrations were applied and are NOT reversed automatically." \
            "      The previous code runs fine on additive tables." \
            "      Plan: $MANIFEST/migration-plan.txt" \
            "      Backup: $BACKUP_FILE" \
            >&2
    fi
}


abort_deployment() {
    local rc="$1"
    local message=""

    shift
    message="$*"

    # With errtrace, the trap also fires inside $(...) and ( ... ).
    # Only the main shell may roll back; a subshell just reports failure.
    if test "$BASHPID" != "$$"
    then
        exit "$rc"
    fi

    if test "$ABORTING" -eq 1
    then
        exit "$rc"
    fi

    ABORTING=1

    trap - ERR INT TERM HUP

    printf 'ERROR: %s\n' "$message" >&2

    record_result \
        "status=failed" \
        "exit_code=$rc" \
        "failure=$message" \
        "mutated=$MUTATED" \
        "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    rollback "$rc"
    cleanup_failed_release
    report_schema_state

    exit "$rc"
}


fail() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}


on_error() {
    local rc="$?"
    local line="${BASH_LINENO[0]:-unknown}"

    abort_deployment \
        "$rc" \
        "schema deployment failed at line $line rc=$rc"
}


on_signal() {
    abort_deployment \
        "$2" \
        "schema deployment interrupted by $1"
}


trap on_error ERR
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP


http_code() {
    local method="$1"
    local path="$2"

    if test "$method" = "HEAD"
    then
        curl -ksS --max-time 5 --head \
            -o /dev/null -w '%{http_code}' \
            "$BASE_URL$path" 2>/dev/null || true
    else
        curl -ksS --max-time 5 -X "$method" \
            -o /dev/null -w '%{http_code}' \
            "$BASE_URL$path" 2>/dev/null || true
    fi
}


require_http() {
    local method="$1"
    local path="$2"
    local expected="$3"
    local actual=""

    actual="$(http_code "$method" "$path")"

    printf '%-8s %-38s expected=%s actual=%s\n' \
        "$method" "$path" "$expected" "$actual"

    test "$actual" = "$expected" ||
        fail "HTTP contract failed: $method $path expected=$expected actual=$actual"
}


# Extract the target tree into a directory readable by the biobank user.
stage_tree() {
    local destination="$1"

    install -d -o root -g biobank -m 2750 "$destination"

    repo_git archive "$TARGET_COMMIT" |
        tar -xf - -C "$destination"

    chown -R root:biobank "$destination"
    find "$destination" -type d -exec chmod 2750 {} +
    find "$destination" -type f -exec chmod 0640 {} +

    test -f "$destination/manage.py" ||
        fail "manage.py missing from staged tree."
}


# Print the planned migrations (one "app.name" per line) for the code in
# the given directory, against the production database. Read-only.
migration_plan() {
    local code_dir="$1"

    (
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
        export PYTHONDONTWRITEBYTECODE=1

        cd "$code_dir"

        runuser \
            -u biobank \
            --preserve-environment \
            -- \
            "$PY" manage.py migrate --plan --noinput
    )
}


plan_names() {
    grep -E '^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]+$' || true
}


echo "============================================================"
echo "B3 LIMS SCHEMA AND STATIC RELEASE DEPLOYMENT"
echo "============================================================"


echo
echo "=== 1. Read-only preflight ==="

test "$(repo_git rev-parse HEAD)" = "$TARGET_COMMIT" ||
    fail "Repository HEAD does not match target commit."

test -z "$(repo_git status --porcelain=v1)" ||
    fail "Repository worktree is not clean."

repo_git cat-file -e "${TARGET_COMMIT}^{commit}" ||
    fail "Target commit does not exist."

test -L "$CURRENT_LINK" ||
    fail "Application current link is missing."

test -L "$STATIC_LINK" ||
    fail "Static current link is missing."

test -d "$STATIC_RELEASE_ROOT" ||
    fail "Static release root is missing."

test -x "$BACKUP_SCRIPT" ||
    fail "PostgreSQL backup script is missing: $BACKUP_SCRIPT"

CURRENT_RELEASE="$(readlink -f "$CURRENT_LINK")"
CURRENT_RELEASE_ID="$(basename "$CURRENT_RELEASE")"
OLD_CURRENT_LINK="$(readlink "$CURRENT_LINK")"

STATIC_BEFORE="$(readlink -f "$STATIC_LINK")"
OLD_STATIC_LINK="$(readlink "$STATIC_LINK")"

case "$CURRENT_RELEASE" in
    "$RELEASE_ROOT"/*) ;;
    *) fail "Current application release is outside canonical release root." ;;
esac

case "$STATIC_BEFORE" in
    "$STATIC_RELEASE_ROOT"/*) ;;
    *) fail "Current static release is outside canonical static release root." ;;
esac

test -d "$CURRENT_RELEASE" ||
    fail "Current application release does not exist."

test -d "$STATIC_BEFORE/admin" ||
    fail "Current static release does not look like collectstatic output."

repo_git cat-file -e "${CURRENT_RELEASE_ID}^{commit}" ||
    fail "Current release is not a Git commit known to repository."

test "$CURRENT_RELEASE_ID" != "$TARGET_COMMIT" ||
    fail "Target commit is already live."

# The target normally descends from the live release. After a deliberate history rewrite
# (for example removing a file from every commit) the hashes change but the content does
# not: accept a target whose history contains a commit with exactly the live release tree.
if ! repo_git merge-base --is-ancestor "$CURRENT_RELEASE_ID" "$TARGET_COMMIT"; then
    LIVE_TREE="$(repo_git rev-parse "${CURRENT_RELEASE_ID}^{tree}")"
    repo_git rev-list --format=%T "$TARGET_COMMIT" | grep -qx "$LIVE_TREE" ||
        fail "Target does not descend from the live release."
    echo "history_rewrite_check=PASS live_tree=$LIVE_TREE found in target history"
fi

test ! -e "$TARGET_RELEASE" ||
    fail "Target immutable release already exists."

test ! -e "$TARGET_STATIC" ||
    fail "Target static release already exists."

test -f "$ENV_FILE" ||
    fail "Runtime environment file is missing."

systemctl is-active --quiet "$SERVICE" ||
    fail "Biobank service is not active."

systemctl is-active --quiet httpd ||
    fail "Apache service is not active."

OLD_PID="$(systemctl show -p MainPID --value "$SERVICE")"

test -n "$OLD_PID" &&
test "$OLD_PID" != "0" ||
    fail "Biobank has no active MainPID."

CHANGED_STATUS="$(
    repo_git diff --name-status --no-renames \
        "$CURRENT_RELEASE_ID" "$TARGET_COMMIT"
)"

CHANGED_PATHS="$(
    printf '%s\n' "$CHANGED_STATUS" | cut -f2-
)"

# Migration files: only additions are acceptable.
MIGRATION_CHANGES="$(
    printf '%s\n' "$CHANGED_STATUS" |
    awk -F '\t' '$2 ~ /(^|\/)migrations\/[^\/]+\.py$/'
)"

if printf '%s\n' "$MIGRATION_CHANGES" |
   awk -F '\t' 'NF && $1 != "A"' |
   grep -q .
then
    printf '%s\n' "$MIGRATION_CHANGES" | awk -F '\t' 'NF && $1 != "A"' >&2
    fail "Existing migration files were edited or deleted; refusing."
fi

EXPECTED_MIGRATIONS="$(
    printf '%s\n' "$MIGRATION_CHANGES" |
    awk -F '\t' 'NF && $1 == "A" { print $2 }' |
    grep -v '/__init__\.py$' |
    sed -E 's#^(.*/)?([^/]+)/migrations/([^/]+)\.py$#\2.\3#' |
    sort || true
)"

STATIC_CHANGES="$(
    printf '%s\n' "$CHANGED_STATUS" |
    awk -F '\t' '$1 != "D" && $2 ~ /(^|\/)static\// { print $2 }'
)"

echo "--- changed paths ---"
printf '%s\n' "$CHANGED_PATHS"
echo "--- migrations added by target ---"
printf '%s\n' "${EXPECTED_MIGRATIONS:-(none)}"
echo "--- static sources changed ---"
printf '%s\n' "${STATIC_CHANGES:-(none)}"

install -d -o root -g biobank -m 2750 "$WORK_DIR"

stage_tree "$WORK_DIR/plan"

echo "--- migration plan against production database ---"

PLAN_OUTPUT="$(migration_plan "$WORK_DIR/plan")"
printf '%s\n' "$PLAN_OUTPUT"

PLAN_LIST="$(printf '%s\n' "$PLAN_OUTPUT" | plan_names | sort)"

# Every pending migration must be one the target adds. An added
# migration that is not pending was already applied (for example by a
# previous attempt that was rolled back), which is fine.
UNEXPECTED_MIGRATIONS="$(
    comm -23 \
        <(printf '%s\n' "$PLAN_LIST" | grep . || true) \
        <(printf '%s\n' "$EXPECTED_MIGRATIONS" | grep . || true)
)"

ALREADY_APPLIED="$(
    comm -13 \
        <(printf '%s\n' "$PLAN_LIST" | grep . || true) \
        <(printf '%s\n' "$EXPECTED_MIGRATIONS" | grep . || true)
)"

test -z "$UNEXPECTED_MIGRATIONS" || {
    echo "--- pending in database but not added by the target ---" >&2
    printf '%s\n' "$UNEXPECTED_MIGRATIONS" >&2
    fail "Migration plan contains migrations the target does not add."
}

echo "--- added migrations already applied ---"
printf '%s\n' "${ALREADY_APPLIED:-(none)}"

PLAN_SHA="$(printf '%s\n' "$PLAN_OUTPUT" | sha256sum | awk '{print $1}')"

rm -rf -- "$WORK_DIR/plan"

echo "target_commit=$TARGET_COMMIT"
echo "current_release=$CURRENT_RELEASE_ID"
echo "static_current=$STATIC_BEFORE"
echo "planned_migrations=$(printf '%s\n' "$PLAN_LIST" | grep -c . || true)"
echo "PLAN_SHA256=$PLAN_SHA"
echo "schema_preflight=PASS"


if test "$MODE" = "preflight"
then
    trap - ERR INT TERM HUP
    cleanup_work_dirs

    echo "preflight_only=PASS"
    echo "production_modified=NO"
    echo
    echo "To deploy exactly this plan:"
    echo "  $0 $TARGET_COMMIT $PLAN_SHA"

    exit 0
fi

test "$PLAN_SHA" = "$APPROVED_PLAN_SHA" ||
    fail "Migration plan changed since it was reviewed. Run --preflight again."


echo
echo "=== 2. Create deployment manifest ==="

install -d -o root -g root -m 0750 "$MANIFEST_ROOT" "$MANIFEST"

MANIFEST_CREATED=1

printf '%s\n' \
    "timestamp=$STAMP" \
    "target_commit=$TARGET_COMMIT" \
    "previous_release=$CURRENT_RELEASE_ID" \
    "previous_current_link=$OLD_CURRENT_LINK" \
    "previous_static=$STATIC_BEFORE" \
    "previous_static_link=$OLD_STATIC_LINK" \
    "plan_sha256=$PLAN_SHA" \
    > "$MANIFEST/metadata.txt"

printf '%s\n' "$CHANGED_STATUS" > "$MANIFEST/changed-paths.txt"
printf '%s\n' "$PLAN_OUTPUT" > "$MANIFEST/migration-plan.txt"

echo "manifest=$MANIFEST"
echo "deployment_manifest=PASS"


echo
echo "=== 3. PostgreSQL backup ==="

BACKUP_LOG="$MANIFEST/backup.log"

runuser -u ladmin -- "$BACKUP_SCRIPT" > "$BACKUP_LOG" 2>&1 || {
    tail -20 "$BACKUP_LOG" >&2
    fail "PostgreSQL backup failed."
}

grep -q '^OK: PostgreSQL backup completed\.$' "$BACKUP_LOG" ||
    fail "PostgreSQL backup did not report success."

BACKUP_FILE="$(sed -n 's/^file=//p' "$BACKUP_LOG" | tail -1)"

test -s "$BACKUP_FILE" ||
    fail "Backup file missing: $BACKUP_FILE"

(cd "$(dirname "$BACKUP_FILE")" && sha256sum -c --quiet "$BACKUP_FILE.sha256") ||
    fail "Backup checksum does not verify."

printf '%s\n' "backup_file=$BACKUP_FILE" >> "$MANIFEST/metadata.txt"

echo "backup_file=$BACKUP_FILE"
echo "postgresql_backup=PASS"


echo
echo "=== 4. Stage exact immutable Git release ==="

stage_tree "$STAGE_RELEASE"

GENERATED_COUNT="$(
    find "$STAGE_RELEASE" \
        \( -type d -name '__pycache__' -o -type f -name '*.pyc' -o -type f -name '*.pyo' \) \
        -print | wc -l
)"

test "$GENERATED_COUNT" -eq 0 ||
    fail "Generated Python artifacts exist in committed release."

RELEASE_GIT_EXECUTABLE_COUNT=0

repo_git ls-tree -rz "$TARGET_COMMIT" > "$MANIFEST/target-tree.z"

test -s "$MANIFEST/target-tree.z" ||
    fail "Git tree inventory is unexpectedly empty."

while IFS= read -r -d "" record
do
    [[ "$record" == *$'\t'* ]] ||
        fail "Malformed Git tree record while restoring executable modes."

    metadata="${record%%$'\t'*}"
    relative="${record#*$'\t'}"
    git_mode="${metadata%% *}"

    test "$git_mode" = "100755" ||
        continue

    case "$relative" in
        /*|..|../*|*/..|*/../*)
            fail "Unsafe executable path in Git tree: $relative"
            ;;
    esac

    test -f "$STAGE_RELEASE/$relative" ||
        fail "Git executable missing from staged release: $relative"

    chmod 0750 -- "$STAGE_RELEASE/$relative"

    RELEASE_GIT_EXECUTABLE_COUNT=$((RELEASE_GIT_EXECUTABLE_COUNT + 1))
done < "$MANIFEST/target-tree.z"

echo "release_git_executable_count=$RELEASE_GIT_EXECUTABLE_COUNT"
echo "immutable_git_stage=PASS"


echo
echo "=== 5. Validate staged application ==="

(
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    export PYTHONDONTWRITEBYTECODE=1

    cd "$STAGE_RELEASE"

    runuser -u biobank --preserve-environment -- \
        "$PY" manage.py check

    runuser -u biobank --preserve-environment -- \
        "$PY" manage.py makemigrations --check --dry-run

    "$PY" manage.py test core bench \
        --settings=biobank.test_settings \
        --verbosity 1
)

GENERATED_COUNT="$(
    find "$STAGE_RELEASE" \
        \( -type d -name '__pycache__' -o -type f -name '*.pyc' -o -type f -name '*.pyo' \) \
        -print | wc -l
)"

test "$GENERATED_COUNT" -eq 0 ||
    fail "Validation generated Python artifacts in staged release."

echo "staged_application_validation=PASS"


echo
echo "=== 6. Build isolated static release ==="

BUILD="$WORK_DIR/build"

install -d -o root -g root -m 0700 "$BUILD" "$BUILD/private-media"

repo_git archive "$TARGET_COMMIT" |
    tar -xf - -C "$BUILD"

(
    cd "$BUILD"

    env -u DATABASE_URL \
        DJANGO_SETTINGS_MODULE=biobank.settings \
        BIOBANK_MEDIA_ROOT="$BUILD/private-media" \
        PYTHONDONTWRITEBYTECODE=1 \
        "$PY" - <<'PY'
from pathlib import Path
from django.conf import settings

base = Path.cwd().resolve()
assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
assert Path(settings.STATIC_ROOT).resolve() == base / "staticfiles"
print("DATABASE=ISOLATED_SQLITE")
print("STATIC_ROOT=ISOLATED")
PY

    env -u DATABASE_URL \
        DJANGO_SETTINGS_MODULE=biobank.settings \
        BIOBANK_MEDIA_ROOT="$BUILD/private-media" \
        PYTHONDONTWRITEBYTECODE=1 \
        "$PY" manage.py collectstatic --noinput --verbosity=1
)

COLLECTED="$BUILD/staticfiles"

test -d "$COLLECTED/admin" ||
    fail "collectstatic output is incomplete."

FIRST_STATIC_ASSET=""

while IFS= read -r source_path
do
    test -n "$source_path" || continue

    relative="${source_path#*static/}"

    test -f "$COLLECTED/$relative" ||
        fail "Changed static source was not collected: $source_path"

    cmp -s "$BUILD/$source_path" "$COLLECTED/$relative" ||
        fail "Collected asset differs from Git source (shadowed?): $source_path"

    test -n "$FIRST_STATIC_ASSET" || FIRST_STATIC_ASSET="$relative"

    echo "collected=$relative"
done <<< "$STATIC_CHANGES"

REMOVED_ASSETS="$(
    comm -23 \
        <(cd "$STATIC_BEFORE" && find . -type f | sort) \
        <(cd "$COLLECTED" && find . -type f | sort) |
    wc -l
)"

echo "collected_file_count=$(find "$COLLECTED" -type f | wc -l)"
echo "assets_no_longer_present=$REMOVED_ASSETS"

(cd "$COLLECTED" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum) \
    > "$MANIFEST/static-sha256.txt"

mv -T "$COLLECTED" "$STAGE_STATIC"

chown -R --reference="$STATIC_BEFORE" "$STAGE_STATIC"
find "$STAGE_STATIC" -type d -exec chmod --reference="$STATIC_BEFORE" {} +
find "$STAGE_STATIC" -type f -exec chmod 0644 {} +

rm -rf -- "$BUILD"

echo "static_build=PASS"


echo
echo "=== 7. Publish immutable releases ==="

mv -T "$STAGE_RELEASE" "$TARGET_RELEASE"
TARGET_RELEASE_CREATED=1

mv -T "$STAGE_STATIC" "$TARGET_STATIC"
TARGET_STATIC_CREATED=1

echo "target_release=$TARGET_RELEASE"
echo "target_static=$TARGET_STATIC"
echo "immutable_publish=PASS"


echo
echo "=== 8. Pre-cutover live boundary ==="

require_http GET "/public/"           200
require_http GET "/public/shipments/" 401
require_http GET "/workspace/"        401

echo "pre_cutover_http_boundary=PASS"


echo
echo "=== 9. Apply reviewed migrations ==="

FINAL_PLAN="$(migration_plan "$TARGET_RELEASE")"

test "$(printf '%s\n' "$FINAL_PLAN" | sha256sum | awk '{print $1}')" = "$PLAN_SHA" ||
    fail "Migration plan changed before apply; nothing applied."

if test -n "$PLAN_LIST"
then
    SCHEMA_APPLIED=1

    (
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
        export PYTHONDONTWRITEBYTECODE=1

        cd "$TARGET_RELEASE"

        runuser -u biobank --preserve-environment -- \
            "$PY" manage.py migrate --noinput

        runuser -u biobank --preserve-environment -- \
            "$PY" manage.py migrate --check
    ) 2>&1 | tee "$MANIFEST/migrate.log"

    echo "schema_migration=PASS"
else
    echo "schema_migration=NONE"
fi


echo
echo "=== 10. Atomic code and static cutover ==="

MUTATED=1

if [[ "$OLD_CURRENT_LINK" == /* ]]
then
    swap_link "$CURRENT_LINK" "$TARGET_RELEASE"
else
    swap_link "$CURRENT_LINK" "releases/$TARGET_COMMIT"
fi

if [[ "$OLD_STATIC_LINK" == /* ]]
then
    swap_link "$STATIC_LINK" "$TARGET_STATIC"
else
    swap_link "$STATIC_LINK" "static-releases/$TARGET_COMMIT"
fi

test "$(readlink -f "$CURRENT_LINK")" = "$TARGET_RELEASE" ||
    fail "Atomic current-link cutover failed."

test "$(readlink -f "$STATIC_LINK")" = "$TARGET_STATIC" ||
    fail "Atomic static-link cutover failed."

systemctl restart "$SERVICE"

echo "atomic_cutover=PASS"


echo
echo "=== 11. Runtime readiness ==="

READY=0
NEW_PID=""
NEW_CWD=""

for attempt in $(seq 1 30)
do
    NEW_PID="$(systemctl show -p MainPID --value "$SERVICE")"

    if test -n "$NEW_PID" && test "$NEW_PID" != "0"
    then
        NEW_CWD="$(readlink -f "/proc/$NEW_PID/cwd" 2>/dev/null || true)"
        PUBLIC_CODE="$(http_code GET "/public/")"
        OPTIONS_CODE="$(http_code OPTIONS "/public/")"

        echo "attempt=$attempt pid=$NEW_PID cwd=$NEW_CWD public=$PUBLIC_CODE options=$OPTIONS_CODE"

        if test "$NEW_CWD" = "$TARGET_RELEASE" &&
           test "$PUBLIC_CODE" = "200" &&
           test "$OPTIONS_CODE" = "405"
        then
            READY=1
            break
        fi
    else
        echo "attempt=$attempt waiting_for_mainpid"
    fi

    sleep 0.5
done

test "$READY" -eq 1 ||
    fail "Target runtime did not satisfy readiness contract."

test "$NEW_PID" != "$OLD_PID" ||
    fail "Biobank MainPID did not change after restart."

echo "runtime_readiness=PASS"


echo
echo "=== 12. Post-cutover HTTP and authentication boundary ==="

require_http GET     "/public/"             200
require_http HEAD    "/public/"             200
require_http OPTIONS "/public/"             405

require_http GET "/public/about/"            200
require_http GET "/public/governance/"       200
require_http GET "/public/samples/"          200
require_http GET "/public/collections/"      200
require_http GET "/public/biobanks/"         200

require_http GET "/public/shipments/"        401
require_http GET "/public/shipments/new/"    401
require_http GET "/biobanks/"                401
require_http GET "/shipments/"               401
require_http GET "/shipments/dashboard/"     401
require_http GET "/workspace/"               401
require_http GET "/internal/bench/"          401

ALLOW_HEADERS="$MANIFEST/public-options.headers"

OPTIONS_STATUS="$(
    curl -ksS --max-time 5 -X OPTIONS \
        -D "$ALLOW_HEADERS" -o /dev/null -w '%{http_code}' \
        "$BASE_URL/public/"
)"

ALLOW="$(
    tr -d '\r' < "$ALLOW_HEADERS" |
    sed -n 's/^[Aa][Ll][Ll][Oo][Ww]:[[:space:]]*//p' |
    head -n 1
)"

test "$OPTIONS_STATUS" = "405" ||
    fail "Public OPTIONS status is not 405."

test "$ALLOW" = "GET, HEAD" ||
    fail "Public Allow header is not GET, HEAD."

echo "post_cutover_http_boundary=PASS"


echo
echo "=== 13. Static and runtime identity ==="

if test -n "$FIRST_STATIC_ASSET"
then
    EXPECTED_SHA="$(sha256sum "$TARGET_STATIC/$FIRST_STATIC_ASSET" | awk '{print $1}')"

    LIVE_SHA="$(
        curl -ksS --fail --max-time 30 \
            --header 'Cache-Control: no-cache' \
            "$BASE_URL/static/$FIRST_STATIC_ASSET?integrity=$TARGET_COMMIT" |
        sha256sum | awk '{print $1}'
    )"

    echo "static_probe=$FIRST_STATIC_ASSET"

    test "$EXPECTED_SHA" = "$LIVE_SHA" ||
        fail "Live static asset does not match the new static release."
fi

FINAL_CURRENT="$(readlink -f "$CURRENT_LINK")"
FINAL_STATIC="$(readlink -f "$STATIC_LINK")"
FINAL_PID="$(systemctl show -p MainPID --value "$SERVICE")"
FINAL_CWD="$(readlink -f "/proc/$FINAL_PID/cwd")"

echo "current=$FINAL_CURRENT"
echo "static_current=$FINAL_STATIC"
echo "pid=$FINAL_PID"
echo "cwd=$FINAL_CWD"

test "$FINAL_CURRENT" = "$TARGET_RELEASE" ||
    fail "current does not resolve to target release."

test "$FINAL_STATIC" = "$TARGET_STATIC" ||
    fail "static-current does not resolve to target static release."

test "$FINAL_CWD" = "$TARGET_RELEASE" ||
    fail "Biobank runtime cwd is not target release."

systemctl is-active --quiet "$SERVICE" ||
    fail "Biobank service is not active after cutover."

systemctl is-active --quiet httpd ||
    fail "Apache service is not active after cutover."

echo "runtime_identity=PASS"


echo
echo "=== 14. Final deployment manifest ==="

printf '%s\n' \
    "status=success" \
    "target_commit=$TARGET_COMMIT" \
    "previous_release=$CURRENT_RELEASE_ID" \
    "previous_static=$STATIC_BEFORE" \
    "current_release=$FINAL_CURRENT" \
    "static_current=$FINAL_STATIC" \
    "schema_applied=$([ "$SCHEMA_APPLIED" -eq 1 ] && echo YES || echo NO)" \
    "plan_sha256=$PLAN_SHA" \
    "backup_file=$BACKUP_FILE" \
    "main_pid=$FINAL_PID" \
    "runtime_cwd=$FINAL_CWD" \
    "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    > "$MANIFEST/result.txt"

trap - ERR INT TERM HUP

cleanup_work_dirs

echo "deployment_manifest=$MANIFEST"

echo
echo "============================================================"
echo "SCHEMA RELEASE DEPLOYMENT=PASS"
echo "LIVE_COMMIT=$TARGET_COMMIT"
echo "ROLLBACK_COMMIT=$CURRENT_RELEASE_ID"
echo "ROLLBACK_STATIC=$STATIC_BEFORE"
echo "STATIC_RELEASE=$FINAL_STATIC"
echo "BACKUP=$BACKUP_FILE"
echo "============================================================"
