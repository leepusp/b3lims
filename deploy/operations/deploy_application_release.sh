#!/usr/bin/env bash

set -euo pipefail
umask 0027

REPO="/home/ladmin/git/biobank"

APP_ROOT="/home/public/apps/biobank"
RELEASE_ROOT="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
STATIC_LINK="$APP_ROOT/static-current"

PY="/home/public/conda/envs/biobank/bin/python"
ENV_FILE="/etc/biobank/runtime.env"

SERVICE="biobank"

BASE_URL="https://davinci.icb.usp.br/b3lims"

MANIFEST_ROOT="$APP_ROOT/storage/manifests/deployment"

MODE="deploy"

if test "${1:-}" = "--preflight"
then
    MODE="preflight"
    shift
fi

TARGET_COMMIT="${1:-}"

test "$#" -eq 1 || {
    printf '%s\n' \
        "ERROR: exactly one target Git commit is required." \
        >&2
    exit 2
}

[[ "$TARGET_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
    printf '%s\n' \
        "ERROR: target must be a full 40-character Git commit." \
        >&2
    exit 2
}

test "${EUID}" -eq 0 || {
    printf '%s\n' \
        "ERROR: run application deployment as root." \
        >&2
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

MANIFEST="$MANIFEST_ROOT/application-${TARGET_COMMIT}-${STAMP}"

CURRENT_RELEASE=""
CURRENT_RELEASE_ID=""
OLD_CURRENT_LINK=""
STATIC_BEFORE=""
OLD_PID=""

TARGET_RELEASE_CREATED=0
MUTATED=0
ROLLBACK_DONE=0
ABORTING=0
MANIFEST_CREATED=0
SUCCESS=0


record_result() {
    test "$MANIFEST_CREATED" -eq 1 ||
        return 0

    printf '%s\n' "$@" \
        >> "$MANIFEST/result.txt" \
        2>/dev/null \
        || true
}


rollback() {
    local rc="$1"
    local rollback_safe=1
    local restored_current=""
    local rollback_pid=""
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

    if test -n "$OLD_CURRENT_LINK"
    then
        local temp_current

        temp_current="$APP_ROOT/.current.rollback.${STAMP}"

        rm -f -- "$temp_current"

        ln -s \
            "$OLD_CURRENT_LINK" \
            "$temp_current" \
            || rollback_safe=0

        if test "$rollback_safe" -eq 1
        then
            mv -Tf \
                "$temp_current" \
                "$CURRENT_LINK" \
                || rollback_safe=0
        fi
    else
        rollback_safe=0
    fi

    restored_current="$(
        readlink -f "$CURRENT_LINK" 2>/dev/null ||
        true
    )"

    if test "$restored_current" != "$CURRENT_RELEASE"
    then
        rollback_safe=0
    fi

    if test "$rollback_safe" -eq 1
    then
        systemctl restart "$SERVICE" \
            >/dev/null 2>&1 \
            || rollback_safe=0
    fi

    if test "$rollback_safe" -eq 1
    then
        sleep 0.5

        rollback_pid="$(
            systemctl show \
                -p MainPID \
                --value \
                "$SERVICE" \
                2>/dev/null
        )"

        if test -z "$rollback_pid" ||
           test "$rollback_pid" = "0"
        then
            rollback_safe=0
        else
            rollback_cwd="$(
                readlink -f \
                    "/proc/$rollback_pid/cwd" \
                    2>/dev/null ||
                true
            )"

            if test "$rollback_cwd" != "$CURRENT_RELEASE"
            then
                rollback_safe=0
            fi
        fi
    fi

    if test "$rollback_safe" -eq 1
    then
        record_result \
            "rollback_contract=RESTORED" \
            "rollback_current=$restored_current" \
            "rollback_cwd=$rollback_cwd"
    else
        record_result \
            "rollback_contract=INCOMPLETE_FAIL_CLOSED"

        printf '%s\n' \
            "ERROR: rollback could not be fully proven; fail closed." \
            >&2
    fi
}


cleanup_failed_release() {
    local current_resolved=""
    local pid=""
    local cwd=""

    set +e

    rm -rf -- \
        "$STAGE_RELEASE"

    if test "$TARGET_RELEASE_CREATED" -ne 1 ||
       test ! -e "$TARGET_RELEASE"
    then
        return
    fi

    current_resolved="$(
        readlink -f "$CURRENT_LINK" 2>/dev/null ||
        true
    )"

    pid="$(
        systemctl show \
            -p MainPID \
            --value \
            "$SERVICE" \
            2>/dev/null
    )"

    if test -n "$pid" &&
       test "$pid" != "0"
    then
        cwd="$(
            readlink -f \
                "/proc/$pid/cwd" \
                2>/dev/null ||
            true
        )"
    fi

    if test "$current_resolved" != "$TARGET_RELEASE" &&
       test "$cwd" != "$TARGET_RELEASE"
    then
        rm -rf -- \
            "$TARGET_RELEASE"
    else
        record_result \
            "warning=failed_target_release_retained" \
            "current=$current_resolved" \
            "runtime_cwd=$cwd"
    fi
}


abort_deployment() {
    local rc="$1"
    local message=""

    shift
    message="$*"

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

    exit "$rc"
}


fail() {
    local message="$*"

    printf 'ERROR: %s\n' "$message" >&2
    return 1
}


on_error() {
    local rc="$?"
    local line="${BASH_LINENO[0]:-unknown}"

    abort_deployment \
        "$rc" \
        "application deployment failed at line $line rc=$rc"
}


on_signal() {
    local signal="$1"
    local rc="$2"

    abort_deployment \
        "$rc" \
        "application deployment interrupted by $signal"
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
        curl \
            -ksS \
            --max-time 5 \
            --head \
            -o /dev/null \
            -w '%{http_code}' \
            "$BASE_URL$path" \
            2>/dev/null \
            || true
    else
        curl \
            -ksS \
            --max-time 5 \
            -X "$method" \
            -o /dev/null \
            -w '%{http_code}' \
            "$BASE_URL$path" \
            2>/dev/null \
            || true
    fi
}


require_http() {
    local method="$1"
    local path="$2"
    local expected="$3"
    local actual=""

    actual="$(
        http_code \
            "$method" \
            "$path"
    )"

    printf '%-8s %-38s expected=%s actual=%s\n' \
        "$method" \
        "$path" \
        "$expected" \
        "$actual"

    test "$actual" = "$expected" ||
        fail \
            "HTTP contract failed: $method $path expected=$expected actual=$actual"
}


echo "============================================================"
echo "B3 LIMS GENERIC APPLICATION RELEASE DEPLOYMENT"
echo "============================================================"


echo
echo "=== 1. Read-only preflight ==="

test "$(repo_git rev-parse HEAD)" = "$TARGET_COMMIT" ||
    fail "Repository HEAD does not match target commit."

test -z "$(repo_git status --porcelain=v1)" ||
    fail "Repository worktree is not clean."

repo_git cat-file \
    -e \
    "${TARGET_COMMIT}^{commit}" ||
    fail "Target commit does not exist."

test -L "$CURRENT_LINK" ||
    fail "Application current link is missing."

test -L "$STATIC_LINK" ||
    fail "Static current link is missing."

CURRENT_RELEASE="$(
    readlink -f "$CURRENT_LINK"
)"

CURRENT_RELEASE_ID="$(
    basename "$CURRENT_RELEASE"
)"

OLD_CURRENT_LINK="$(
    readlink "$CURRENT_LINK"
)"

STATIC_BEFORE="$(
    readlink -f "$STATIC_LINK"
)"

case "$CURRENT_RELEASE" in
    "$RELEASE_ROOT"/*)
        ;;
    *)
        fail \
            "Current application release is outside canonical release root."
        ;;
esac

test -d "$CURRENT_RELEASE" ||
    fail "Current application release does not exist."

repo_git cat-file \
    -e \
    "${CURRENT_RELEASE_ID}^{commit}" ||
    fail "Current release is not a Git commit known to repository."

test "$CURRENT_RELEASE_ID" != "$TARGET_COMMIT" ||
    fail "Target commit is already live."

test ! -e "$TARGET_RELEASE" ||
    fail "Target immutable release already exists."

test ! -e "$STAGE_RELEASE" ||
    fail "Target staging release already exists."

test -f "$ENV_FILE" ||
    fail "Runtime environment file is missing."

systemctl is-active --quiet "$SERVICE" ||
    fail "Biobank service is not active."

systemctl is-active --quiet httpd ||
    fail "Apache service is not active."

OLD_PID="$(
    systemctl show \
        -p MainPID \
        --value \
        "$SERVICE"
)"

test -n "$OLD_PID" &&
test "$OLD_PID" != "0" ||
    fail "Biobank has no active MainPID."

CHANGED_PATHS="$(
    repo_git diff \
        --name-only \
        "$CURRENT_RELEASE_ID" \
        "$TARGET_COMMIT"
)"

printf '%s\n' "$CHANGED_PATHS"

if printf '%s\n' "$CHANGED_PATHS" |
   grep -Eq '(^|/)migrations/.*\.py$'
then
    fail \
        "Generic application deploy refuses migration changes."
fi

if printf '%s\n' "$CHANGED_PATHS" |
   grep -Eq '(^|/)static/'
then
    fail \
        "Generic application deploy refuses static asset changes."
fi

echo "target_commit=$TARGET_COMMIT"
echo "current_release=$CURRENT_RELEASE_ID"
echo "static_current=$STATIC_BEFORE"
echo "application_preflight=PASS"


if test "$MODE" = "preflight"
then
    trap - ERR INT TERM HUP

    echo "preflight_only=PASS"
    echo "production_modified=NO"

    exit 0
fi


echo
echo "=== 2. Create deployment manifest ==="

install \
    -d \
    -o root \
    -g root \
    -m 0750 \
    "$MANIFEST_ROOT" \
    "$MANIFEST"

MANIFEST_CREATED=1

printf '%s\n' \
    "timestamp=$STAMP" \
    "target_commit=$TARGET_COMMIT" \
    "previous_release=$CURRENT_RELEASE_ID" \
    "previous_current_link=$OLD_CURRENT_LINK" \
    "static_current=$STATIC_BEFORE" \
    "migration_changes=NO" \
    "static_changes=NO" \
    > "$MANIFEST/metadata.txt"

printf '%s\n' \
    "$CHANGED_PATHS" \
    > "$MANIFEST/changed-paths.txt"

echo "manifest=$MANIFEST"
echo "deployment_manifest=PASS"


echo
echo "=== 3. Stage exact immutable Git release ==="

install \
    -d \
    -o root \
    -g biobank \
    -m 2750 \
    "$STAGE_RELEASE"

repo_git archive "$TARGET_COMMIT" |
    tar -xf - \
        -C "$STAGE_RELEASE"

GENERATED_COUNT="$(
    find "$STAGE_RELEASE" \
        \( \
            -type d -name '__pycache__' \
            -o \
            -type f -name '*.pyc' \
            -o \
            -type f -name '*.pyo' \
        \) \
        -print |
    wc -l
)"

echo "generated_python_count=$GENERATED_COUNT"

test "$GENERATED_COUNT" -eq 0 ||
    fail \
        "Generated Python artifacts exist in committed release."

chown -R \
    root:biobank \
    "$STAGE_RELEASE"

find \
    "$STAGE_RELEASE" \
    -type d \
    -exec chmod 2750 {} +

find \
    "$STAGE_RELEASE" \
    -type f \
    -exec chmod 0640 {} +

RELEASE_GIT_EXECUTABLE_COUNT=0

GIT_TREE_FILE="$MANIFEST/target-tree.z"

repo_git ls-tree \
    -rz \
    "$TARGET_COMMIT" \
    > "$GIT_TREE_FILE"

test -s "$GIT_TREE_FILE" ||
    fail \
        "Git tree inventory is unexpectedly empty."

while IFS= read -r -d "" record
do
    [[ "$record" == *$'\t'* ]] ||
        fail \
            "Malformed Git tree record while restoring executable modes."

    metadata="${record%%$'\t'*}"
    relative="${record#*$'\t'}"
    git_mode="${metadata%% *}"

    test "$git_mode" = "100755" ||
        continue

    case "$relative" in
        /*|..|../*|*/..|*/../*)
            fail \
                "Unsafe executable path in Git tree: $relative"
            ;;
    esac

    release_path="$STAGE_RELEASE/$relative"

    test -f "$release_path" ||
        fail \
            "Git executable missing from staged release: $relative"

    chmod 0750 -- \
        "$release_path"

    test -x "$release_path" ||
        fail \
            "Executable mode restoration failed: $relative"

    RELEASE_GIT_EXECUTABLE_COUNT=$((RELEASE_GIT_EXECUTABLE_COUNT + 1))
done < "$GIT_TREE_FILE"

echo "release_git_executable_count=$RELEASE_GIT_EXECUTABLE_COUNT"
echo "git_executable_mode_contract=PASS"

test -f "$STAGE_RELEASE/manage.py" ||
    fail "manage.py missing from staged application."

echo "immutable_git_stage=PASS"


echo
echo "=== 4. Validate staged application before publication ==="

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export PYTHONDONTWRITEBYTECODE=1

(
    cd "$STAGE_RELEASE"

    runuser \
        -u biobank \
        --preserve-environment \
        -- \
        "$PY" manage.py check

    runuser \
        -u biobank \
        --preserve-environment \
        -- \
        "$PY" manage.py makemigrations \
            --check \
            --dry-run

    "$PY" manage.py test \
        core \
        --settings=biobank.test_settings \
        --verbosity 1
)

GENERATED_COUNT="$(
    find "$STAGE_RELEASE" \
        \( \
            -type d -name '__pycache__' \
            -o \
            -type f -name '*.pyc' \
            -o \
            -type f -name '*.pyo' \
        \) \
        -print |
    wc -l
)"

echo "post_validation_generated_python_count=$GENERATED_COUNT"

test "$GENERATED_COUNT" -eq 0 ||
    fail \
        "Validation generated Python artifacts in staged release."

echo "staged_application_validation=PASS"


echo
echo "=== 5. Publish immutable release ==="

mv \
    "$STAGE_RELEASE" \
    "$TARGET_RELEASE"

TARGET_RELEASE_CREATED=1

test -d "$TARGET_RELEASE" ||
    fail "Immutable target publication failed."

echo "target_release=$TARGET_RELEASE"
echo "immutable_publish=PASS"


echo
echo "=== 6. Pre-cutover live boundary ==="

require_http \
    GET \
    "/public/" \
    200

require_http \
    GET \
    "/public/shipments/" \
    401

require_http \
    GET \
    "/workspace/" \
    401

echo "pre_cutover_http_boundary=PASS"


echo
echo "=== 7. Atomic application cutover ==="

MUTATED=1

TEMP_CURRENT="$APP_ROOT/.current.${TARGET_COMMIT}.${STAMP}"

rm -f -- \
    "$TEMP_CURRENT"

ln -s \
    "releases/$TARGET_COMMIT" \
    "$TEMP_CURRENT"

mv -Tf \
    "$TEMP_CURRENT" \
    "$CURRENT_LINK"

test "$(readlink -f "$CURRENT_LINK")" = "$TARGET_RELEASE" ||
    fail "Atomic current-link cutover failed."

systemctl restart "$SERVICE"

echo "atomic_application_cutover=PASS"


echo
echo "=== 8. Runtime readiness ==="

READY=0
NEW_PID=""
NEW_CWD=""

for attempt in $(seq 1 30)
do
    NEW_PID="$(
        systemctl show \
            -p MainPID \
            --value \
            "$SERVICE"
    )"

    if test -n "$NEW_PID" &&
       test "$NEW_PID" != "0"
    then
        NEW_CWD="$(
            readlink -f \
                "/proc/$NEW_PID/cwd" \
                2>/dev/null ||
            true
        )"

        PUBLIC_CODE="$(
            http_code \
                GET \
                "/public/"
        )"

        OPTIONS_CODE="$(
            http_code \
                OPTIONS \
                "/public/"
        )"

        printf '%s\n' \
            "attempt=$attempt pid=$NEW_PID cwd=$NEW_CWD public=$PUBLIC_CODE options=$OPTIONS_CODE"

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
    fail \
        "Target runtime did not satisfy readiness contract."

test "$NEW_PID" != "$OLD_PID" ||
    fail \
        "Biobank MainPID did not change after restart."

echo "runtime_readiness=PASS"


echo
echo "=== 9. Post-cutover HTTP and authentication boundary ==="

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

echo "post_cutover_http_boundary=PASS"


echo
echo "=== 10. Allow header boundary ==="

ALLOW_HEADERS="$MANIFEST/public-options.headers"

OPTIONS_STATUS="$(
    curl \
        -ksS \
        --max-time 5 \
        -X OPTIONS \
        -D "$ALLOW_HEADERS" \
        -o /dev/null \
        -w '%{http_code}' \
        "$BASE_URL/public/"
)"

ALLOW="$(
    tr -d '\r' \
        < "$ALLOW_HEADERS" |
    sed -n \
        's/^[Aa][Ll][Ll][Oo][Ww]:[[:space:]]*//p' |
    head -n 1
)"

echo "options_status=$OPTIONS_STATUS"
echo "normalized_allow=<$ALLOW>"

test "$OPTIONS_STATUS" = "405" ||
    fail "Public OPTIONS status is not 405."

test "$ALLOW" = "GET, HEAD" ||
    fail "Public Allow header is not GET, HEAD."

echo "allow_header_contract=PASS"


echo
echo "=== 11. Static and runtime identity boundary ==="

STATIC_AFTER="$(
    readlink -f "$STATIC_LINK"
)"

FINAL_CURRENT="$(
    readlink -f "$CURRENT_LINK"
)"

FINAL_PID="$(
    systemctl show \
        -p MainPID \
        --value \
        "$SERVICE"
)"

FINAL_CWD="$(
    readlink -f \
        "/proc/$FINAL_PID/cwd"
)"

echo "current=$FINAL_CURRENT"
echo "static_current=$STATIC_AFTER"
echo "pid=$FINAL_PID"
echo "cwd=$FINAL_CWD"

test "$STATIC_AFTER" = "$STATIC_BEFORE" ||
    fail "static-current changed during application-only deploy."

test "$FINAL_CURRENT" = "$TARGET_RELEASE" ||
    fail "current does not resolve to target release."

test "$FINAL_CWD" = "$TARGET_RELEASE" ||
    fail "Biobank runtime cwd is not target release."

systemctl is-active --quiet "$SERVICE" ||
    fail "Biobank service is not active after cutover."

systemctl is-active --quiet httpd ||
    fail "Apache service is not active after cutover."

echo "static_boundary=PASS"
echo "runtime_identity=PASS"


echo
echo "=== 12. Final deployment manifest ==="

printf '%s\n' \
    "status=success" \
    "target_commit=$TARGET_COMMIT" \
    "previous_release=$CURRENT_RELEASE_ID" \
    "current_release=$FINAL_CURRENT" \
    "static_current=$STATIC_AFTER" \
    "main_pid=$FINAL_PID" \
    "runtime_cwd=$FINAL_CWD" \
    "public_http=200" \
    "public_options_http=405" \
    "public_allow=GET, HEAD" \
    "public_shipments_http=401" \
    "workspace_http=401" \
    "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    > "$MANIFEST/result.txt"

SUCCESS=1

trap - ERR INT TERM HUP

echo "deployment_manifest=$MANIFEST"

echo
echo "============================================================"
echo "GENERIC APPLICATION RELEASE DEPLOYMENT=PASS"
echo "LIVE_COMMIT=$TARGET_COMMIT"
echo "ROLLBACK_COMMIT=$CURRENT_RELEASE_ID"
echo "STATIC_RELEASE=$STATIC_AFTER"
echo "============================================================"
