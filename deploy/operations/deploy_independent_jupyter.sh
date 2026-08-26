#!/usr/bin/env bash

set -Eeuo pipefail
umask 0027

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}

test "${EUID}" -eq 0 ||
    fail "Run this deployment as root."

MODE="deploy"

if test "${1:-}" = "--preflight"
then
    MODE="preflight"
    shift
fi

TARGET_COMMIT="${1:-}"

test "$#" -eq 1 ||
    fail "Exactly one target Git commit is required."

[[ "$TARGET_COMMIT" =~ ^[0-9a-f]{40}$ ]] ||
    fail "A full 40-character target Git commit is required."

REPO="/home/ladmin/git/biobank"

APP_ROOT="/home/public/apps/biobank"
RELEASE_ROOT="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"

PY="/home/public/conda/envs/biobank/bin/python"
ENV_FILE="/etc/biobank/runtime.env"

BIOBANK_CONF="/etc/httpd/conf.d/biobank.conf"

HTTPD_BIOBANK_ROOT="/etc/httpd/biobank"
JUPYTER_CONF="$HTTPD_BIOBANK_ROOT/biobank-jupyter.conf"
JUPYTER_LUA="$HTTPD_BIOBANK_ROOT/biobank_jupyter_proxy.lua"

LEGACY_OOD_PROXY="/etc/ood/config/biobank-node-proxy.conf"

LIVE_BROKER="/usr/local/sbin/biobank-jupyter-server-broker"
LIVE_RECONCILER="/usr/local/sbin/biobank-jupyter-proxy-reconciler"

LIVE_SUDOERS="/etc/sudoers.d/biobank-runtime-brokers"

SERVICE_UNIT="/etc/systemd/system/biobank-jupyter-proxy-reconciler.service"
TIMER_UNIT="/etc/systemd/system/biobank-jupyter-proxy-reconciler.timer"

BINDING_ROOT="/run/biobank-jupyter-proxy"

EXPECTED_CURRENT_RELEASE="27ad1ae9b9d8bd92998bbe9697ec6631c25b5abc"

EXPECTED_BIOBANK_CONF_SHA256="8f7f08060320b804dcb8290f14c51df5c1db7d7c95ac3eb80956d77dfa68be40"
EXPECTED_OOD_PROXY_SHA256="a837f68e3898cf3d8b76ba804824af5c323a1b690a28ebd6ac9521d2b4bd7286"
EXPECTED_BROKER_SHA256="ab828f4ebbb04dabbaed6cd179bf58d5e58381b404276ffc132607ffc65e3813"

SOURCE_APACHE="$REPO/deploy/apache/biobank.conf"
SOURCE_JUPYTER_CONF="$REPO/deploy/apache/biobank-jupyter.conf"
SOURCE_JUPYTER_LUA="$REPO/deploy/apache/biobank_jupyter_proxy.lua"

SOURCE_BROKER="$REPO/deploy/sbin/biobank-jupyter-server-broker"
SOURCE_RECONCILER="$REPO/deploy/sbin/biobank-jupyter-proxy-reconciler"

SOURCE_SUDOERS="$REPO/deploy/sudoers/biobank-runtime-brokers"

SOURCE_SERVICE="$REPO/deploy/systemd/biobank-jupyter-proxy-reconciler.service"
SOURCE_TIMER="$REPO/deploy/systemd/biobank-jupyter-proxy-reconciler.timer"

repo_git() {
    runuser -u ladmin -- \
        git -C "$REPO" "$@"
}

sha() {
    sha256sum "$1" |
        awk '{print $1}'
}

STAMP="$(
    date -u '+%Y%m%dT%H%M%SZ'
)"

MANIFEST_ROOT="$APP_ROOT/storage/manifests/deployment"
MANIFEST="$MANIFEST_ROOT/independent-jupyter-${STAMP}"

TARGET_RELEASE="$RELEASE_ROOT/$TARGET_COMMIT"
STAGE_RELEASE="$RELEASE_ROOT/.${TARGET_COMMIT}.${STAMP}.staging"

OLD_CURRENT_LINK=""
BIOBANK_WAS_ACTIVE=0
HTTPD_WAS_ACTIVE=0

TARGET_RELEASE_CREATED=0
MUTATED=0
SUCCESS=0


rollback() {
    local rc="$1"
    local rollback_safe=1
    local restored_current=""

    set +e

    if test "$MUTATED" -ne 1
    then
        return
    fi

    printf '%s\n' \
        "status=rollback" \
        "exit_code=$rc" \
        "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        >> "$MANIFEST/result.txt" \
        2>/dev/null \
        || true

    systemctl disable --now \
        biobank-jupyter-proxy-reconciler.timer \
        >/dev/null 2>&1 \
        || true

    systemctl stop biobank \
        >/dev/null 2>&1 \
        || true

    if test -n "$OLD_CURRENT_LINK"
    then
        TEMP_CURRENT="$APP_ROOT/.current.rollback.${STAMP}"

        rm -f -- "$TEMP_CURRENT"

        ln -s \
            "$OLD_CURRENT_LINK" \
            "$TEMP_CURRENT"

        mv -Tf \
            "$TEMP_CURRENT" \
            "$CURRENT_LINK"
    fi

    if test -f "$MANIFEST/biobank.conf.before"
    then
        install \
            -o root \
            -g root \
            -m 0644 \
            "$MANIFEST/biobank.conf.before" \
            "$BIOBANK_CONF"
    fi

    if test -f "$MANIFEST/biobank-node-proxy.conf.before"
    then
        install \
            -o root \
            -g apache \
            -m 0640 \
            "$MANIFEST/biobank-node-proxy.conf.before" \
            "$LEGACY_OOD_PROXY"
    fi

    if test -f "$MANIFEST/jupyter-server-broker.before"
    then
        install \
            -o root \
            -g root \
            -m 0755 \
            "$MANIFEST/jupyter-server-broker.before" \
            "$LIVE_BROKER"
    fi

    if test -f "$MANIFEST/runtime-brokers.sudoers.before"
    then
        install \
            -o root \
            -g root \
            -m 0440 \
            "$MANIFEST/runtime-brokers.sudoers.before" \
            "$LIVE_SUDOERS"
    fi

    rm -f -- \
        "$LIVE_RECONCILER" \
        "$SERVICE_UNIT" \
        "$TIMER_UNIT"

    rm -rf -- \
        "$HTTPD_BIOBANK_ROOT"

    rmdir \
        "$BINDING_ROOT" \
        >/dev/null 2>&1 \
        || true

    rm -rf -- \
        "$STAGE_RELEASE"

    systemctl daemon-reload \
        >/dev/null 2>&1 \
        || rollback_safe=0

    restored_current="$(
        readlink "$CURRENT_LINK" 2>/dev/null ||
        true
    )"

    if test "$restored_current" != "$OLD_CURRENT_LINK"
    then
        rollback_safe=0
    fi

    cmp -s \
        "$MANIFEST/biobank.conf.before" \
        "$BIOBANK_CONF" \
        || rollback_safe=0

    cmp -s \
        "$MANIFEST/biobank-node-proxy.conf.before" \
        "$LEGACY_OOD_PROXY" \
        || rollback_safe=0

    cmp -s \
        "$MANIFEST/jupyter-server-broker.before" \
        "$LIVE_BROKER" \
        || rollback_safe=0

    cmp -s \
        "$MANIFEST/runtime-brokers.sudoers.before" \
        "$LIVE_SUDOERS" \
        || rollback_safe=0

    test ! -e "$HTTPD_BIOBANK_ROOT" ||
        rollback_safe=0

    test ! -e "$LIVE_RECONCILER" ||
        rollback_safe=0

    test ! -e "$SERVICE_UNIT" ||
        rollback_safe=0

    test ! -e "$TIMER_UNIT" ||
        rollback_safe=0

    test ! -e "$BINDING_ROOT" ||
        rollback_safe=0

    if httpd -t \
        >/dev/null 2>&1
    then
        if test "$HTTPD_WAS_ACTIVE" -eq 1
        then
            systemctl reload httpd \
                >/dev/null 2>&1 \
                || rollback_safe=0
        fi
    else
        rollback_safe=0
    fi

    if test "$BIOBANK_WAS_ACTIVE" -eq 1
    then
        if test "$rollback_safe" -eq 1
        then
            systemctl start biobank \
                >/dev/null 2>&1 \
                || rollback_safe=0
        else
            printf '%s\n' \
                "rollback_biobank_restart=SKIPPED_FAIL_CLOSED" \
                >> "$MANIFEST/result.txt" \
                2>/dev/null \
                || true
        fi
    fi

    if test "$rollback_safe" -eq 1
    then
        printf '%s\n' \
            "rollback_contract=RESTORED" \
            >> "$MANIFEST/result.txt" \
            2>/dev/null \
            || true
    else
        printf '%s\n' \
            "rollback_contract=INCOMPLETE_FAIL_CLOSED" \
            >> "$MANIFEST/result.txt" \
            2>/dev/null \
            || true
    fi
}


cleanup_failed_release() {
    local current_resolved=""

    set +e

    rm -rf -- \
        "$STAGE_RELEASE"

    if test "$TARGET_RELEASE_CREATED" -eq 1 &&
       test -e "$TARGET_RELEASE"
    then
        current_resolved="$(
            readlink -f "$CURRENT_LINK" 2>/dev/null ||
            true
        )"

        if test "$current_resolved" != "$TARGET_RELEASE"
        then
            rm -rf -- \
                "$TARGET_RELEASE"
        else
            printf '%s\n' \
                "warning=target_release_is_still_current" \
                >> "$MANIFEST/result.txt" \
                2>/dev/null \
                || true
        fi
    fi
}


on_error() {
    local rc="$?"
    local line="${BASH_LINENO[0]:-unknown}"

    trap - ERR INT TERM HUP

    printf 'ERROR: deployment failed at line %s rc=%s\n' \
        "$line" \
        "$rc" \
        >&2

    rollback "$rc"
    cleanup_failed_release

    exit "$rc"
}


on_signal() {
    local signal="$1"
    local rc="$2"

    trap - ERR INT TERM HUP

    printf 'ERROR: deployment interrupted by %s rc=%s\n' \
        "$signal" \
        "$rc" \
        >&2

    rollback "$rc"
    cleanup_failed_release

    exit "$rc"
}


trap on_error ERR
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP


echo "============================================================"
echo "1. CUTOVER PREFLIGHT"
echo "============================================================"

test "$(repo_git rev-parse HEAD)" = "$TARGET_COMMIT" ||
    fail "Repository HEAD does not match target commit."

test "$(repo_git rev-parse origin/main)" = "$TARGET_COMMIT" ||
    fail "origin/main does not match target commit."

test -z "$(repo_git status --porcelain=v1)" ||
    fail "Repository is not clean."

for file in \
    "$SOURCE_APACHE" \
    "$SOURCE_JUPYTER_CONF" \
    "$SOURCE_JUPYTER_LUA" \
    "$SOURCE_BROKER" \
    "$SOURCE_RECONCILER" \
    "$SOURCE_SUDOERS" \
    "$SOURCE_SERVICE" \
    "$SOURCE_TIMER"
do
    test -f "$file" ||
        fail "Required deployment source is missing: $file"
done

test ! -e "$REPO/deploy/ood/biobank-node-proxy.conf" ||
    fail "Legacy OOD proxy source is still present."

test ! -e "$REPO/deploy/ood/biobank_jupyter_session_authz.lua" ||
    fail "Legacy OOD authz source is still present."

CURRENT_RELEASE="$(
    readlink -f "$CURRENT_LINK"
)"

CURRENT_RELEASE_ID="$(
    basename "$CURRENT_RELEASE"
)"

test "$CURRENT_RELEASE_ID" = "$EXPECTED_CURRENT_RELEASE" ||
    fail "Unexpected current application release."

test ! -e "$TARGET_RELEASE" ||
    fail "Target release already exists."

test ! -e "$STAGE_RELEASE" ||
    fail "Target staging directory already exists."

test ! -e "$HTTPD_BIOBANK_ROOT" ||
    fail "Biobank HTTPD namespace already exists."

test ! -e "$LIVE_RECONCILER" ||
    fail "Jupyter proxy reconciler is already installed."

test ! -e "$SERVICE_UNIT" ||
    fail "Reconciler service unit is already installed."

test ! -e "$TIMER_UNIT" ||
    fail "Reconciler timer unit is already installed."

test ! -e "$BINDING_ROOT" ||
    fail "Proxy binding root already exists."

test -f "$LEGACY_OOD_PROXY" ||
    fail "Legacy OOD proxy is not present."

test "$(sha "$BIOBANK_CONF")" = \
    "$EXPECTED_BIOBANK_CONF_SHA256" ||
    fail "Live Biobank Apache config has drifted."

test "$(sha "$LEGACY_OOD_PROXY")" = \
    "$EXPECTED_OOD_PROXY_SHA256" ||
    fail "Legacy OOD proxy has drifted."

test "$(sha "$LIVE_BROKER")" = \
    "$EXPECTED_BROKER_SHA256" ||
    fail "Live Jupyter broker has drifted."

cmp -s \
    "$SOURCE_SUDOERS" \
    "$LIVE_SUDOERS" ||
    fail "Live runtime broker sudoers differs from reviewed source."

grep -qxF \
    'BIOBANK_JUPYTER_SERVER_RUNNER=/usr/local/sbin/biobank-jupyter-server-broker' \
    "$ENV_FILE"

grep -qxF \
    'BIOBANK_LAB_TOOLS_STORAGE_RUNNER=/usr/local/sbin/biobank-user-storage-broker' \
    "$ENV_FILE"

ACTIVE="$(
    squeue \
        --noheader \
        --format='%i|%u|%j|%T|%N' |
    grep -E '\|biobank_notebook_[0-9]+\|' \
    || true
)"

test -z "$ACTIVE" ||
    fail "Managed Jupyter sessions are active."

systemctl is-active --quiet httpd
HTTPD_WAS_ACTIVE=1

systemctl is-active --quiet biobank
BIOBANK_WAS_ACTIVE=1

OLD_CURRENT_LINK="$(
    readlink "$CURRENT_LINK"
)"

echo "target_commit=$TARGET_COMMIT"
echo "current_release=$CURRENT_RELEASE_ID"
echo "active_managed_jupyter=NO"
echo "cutover_preflight=PASS"

if test "$MODE" = "preflight"
then
    trap - ERR INT TERM HUP
    echo "preflight_only=PASS"
    echo "production_modified=NO"
    exit 0
fi


echo
echo "============================================================"
echo "2. CREATE DEPLOYMENT MANIFEST"
echo "============================================================"

install \
    -d \
    -o root \
    -g root \
    -m 0750 \
    "$MANIFEST_ROOT" \
    "$MANIFEST"

cp -a \
    "$BIOBANK_CONF" \
    "$MANIFEST/biobank.conf.before"

cp -a \
    "$LEGACY_OOD_PROXY" \
    "$MANIFEST/biobank-node-proxy.conf.before"

cp -a \
    "$LIVE_BROKER" \
    "$MANIFEST/jupyter-server-broker.before"

cp -a \
    "$LIVE_SUDOERS" \
    "$MANIFEST/runtime-brokers.sudoers.before"

printf '%s\n' \
    "timestamp=$STAMP" \
    "target_commit=$TARGET_COMMIT" \
    "previous_current_link=$OLD_CURRENT_LINK" \
    "previous_current_release=$CURRENT_RELEASE_ID" \
    "static_current=$(readlink "$APP_ROOT/static-current")" \
    "ood_portal_yml_modified=NO" \
    "ood_portal_generated_modified=NO" \
    > "$MANIFEST/metadata.txt"

sha256sum \
    "$MANIFEST/biobank.conf.before" \
    "$MANIFEST/biobank-node-proxy.conf.before" \
    "$MANIFEST/jupyter-server-broker.before" \
    "$MANIFEST/runtime-brokers.sudoers.before" \
    > "$MANIFEST/before.sha256"

echo "manifest=$MANIFEST"
echo "deployment_manifest=PASS"


echo
echo "============================================================"
echo "3. STAGE IMMUTABLE APPLICATION RELEASE"
echo "============================================================"

install \
    -d \
    -o root \
    -g biobank \
    -m 2750 \
    "$STAGE_RELEASE"

repo_git archive "$TARGET_COMMIT" |
    tar -xf - \
        -C "$STAGE_RELEASE"

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

mv \
    "$STAGE_RELEASE" \
    "$TARGET_RELEASE"

TARGET_RELEASE_CREATED=1

test -f "$TARGET_RELEASE/manage.py"

echo "target_release=$TARGET_RELEASE"
echo "immutable_release_staged=PASS"


echo
echo "============================================================"
echo "4. VALIDATE STAGED APPLICATION"
echo "============================================================"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

(
    cd "$TARGET_RELEASE"

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
)

echo "staged_application_validation=PASS"


echo
echo "============================================================"
echo "5. ENTER CONTROL-PLANE QUIESCENCE"
echo "============================================================"

MUTATED=1

systemctl stop biobank

if systemctl is-active --quiet biobank
then
    fail "Biobank did not stop for the controlled cutover."
fi

ACTIVE="$(
    squeue \
        --noheader \
        --format='%i|%u|%j|%T|%N' |
    grep -E '\|biobank_notebook_[0-9]+\|' \
    || true
)"

test -z "$ACTIVE" ||
    fail "A managed Jupyter session appeared before cutover."

echo "biobank_control_plane=QUIESCENT"
echo "active_managed_jupyter=NO"
echo "pre_mutation_quiescence=PASS"


echo
echo "============================================================"
echo "6. INSTALL RUNTIME COMPONENTS"
echo "============================================================"

install \
    -o root \
    -g root \
    -m 0755 \
    "$SOURCE_BROKER" \
    "${LIVE_BROKER}.new"

mv -Tf \
    "${LIVE_BROKER}.new" \
    "$LIVE_BROKER"

install \
    -o root \
    -g root \
    -m 0755 \
    "$SOURCE_RECONCILER" \
    "${LIVE_RECONCILER}.new"

mv -Tf \
    "${LIVE_RECONCILER}.new" \
    "$LIVE_RECONCILER"

install \
    -o root \
    -g root \
    -m 0440 \
    "$SOURCE_SUDOERS" \
    "${LIVE_SUDOERS}.new"

visudo -cf \
    "${LIVE_SUDOERS}.new"

mv -Tf \
    "${LIVE_SUDOERS}.new" \
    "$LIVE_SUDOERS"

install \
    -o root \
    -g root \
    -m 0644 \
    "$SOURCE_SERVICE" \
    "${SERVICE_UNIT}.new"

mv -Tf \
    "${SERVICE_UNIT}.new" \
    "$SERVICE_UNIT"

install \
    -o root \
    -g root \
    -m 0644 \
    "$SOURCE_TIMER" \
    "${TIMER_UNIT}.new"

mv -Tf \
    "${TIMER_UNIT}.new" \
    "$TIMER_UNIT"

install \
    -d \
    -o root \
    -g biobank-proxy \
    -m 0750 \
    "$BINDING_ROOT"

echo "runtime_components_installed=PASS"


echo
echo "============================================================"
echo "7. INSTALL BIOBANK-OWNED APACHE DATA PLANE"
echo "============================================================"

install \
    -d \
    -o root \
    -g apache \
    -m 0750 \
    "$HTTPD_BIOBANK_ROOT"

install \
    -o root \
    -g apache \
    -m 0640 \
    "$SOURCE_JUPYTER_CONF" \
    "${JUPYTER_CONF}.new"

mv -Tf \
    "${JUPYTER_CONF}.new" \
    "$JUPYTER_CONF"

install \
    -o root \
    -g apache \
    -m 0640 \
    "$SOURCE_JUPYTER_LUA" \
    "${JUPYTER_LUA}.new"

mv -Tf \
    "${JUPYTER_LUA}.new" \
    "$JUPYTER_LUA"

install \
    -o root \
    -g root \
    -m 0644 \
    "$SOURCE_APACHE" \
    "${BIOBANK_CONF}.new"

mv -Tf \
    "${BIOBANK_CONF}.new" \
    "$BIOBANK_CONF"

echo "biobank_httpd_namespace_installed=PASS"


echo
echo "============================================================"
echo "8. RETIRE ACTIVE LEGACY OOD PROXY FILE"
echo "============================================================"

rm -f -- \
    "$LEGACY_OOD_PROXY"

test ! -e "$LEGACY_OOD_PROXY"

# The generated OOD vhost may retain its IncludeOptional line.
# No OOD YAML/template/generator mutation is part of this cutover.
grep -qF \
    'IncludeOptional "/etc/ood/config/biobank-node-proxy.conf"' \
    /etc/httpd/conf.d/ood-portal.conf

echo "legacy_ood_proxy_file=ABSENT"
echo "ood_generator_modified=NO"


echo
echo "============================================================"
echo "9. PRE-CUTOVER LIVE FILESYSTEM VALIDATION"
echo "============================================================"

visudo -cf \
    /etc/sudoers

systemctl daemon-reload

httpd -t

systemctl start \
    biobank-jupyter-proxy-reconciler.service

systemctl enable --now \
    biobank-jupyter-proxy-reconciler.timer

systemctl is-enabled --quiet \
    biobank-jupyter-proxy-reconciler.timer

systemctl is-active --quiet \
    biobank-jupyter-proxy-reconciler.timer

echo "live_filesystem_pre_cutover=PASS"


echo
echo "============================================================"
echo "10. CONTROLLED APPLICATION / APACHE CUTOVER"
echo "============================================================"

TEMP_CURRENT="$APP_ROOT/.current.${STAMP}"

rm -f -- \
    "$TEMP_CURRENT"

ln -s \
    "releases/$TARGET_COMMIT" \
    "$TEMP_CURRENT"

mv -Tf \
    "$TEMP_CURRENT" \
    "$CURRENT_LINK"

test "$(readlink -f "$CURRENT_LINK")" = \
    "$TARGET_RELEASE"

httpd -t

systemctl reload httpd

systemctl start biobank

systemctl is-active --quiet httpd
systemctl is-active --quiet biobank

echo "atomic_logical_cutover=PASS"


echo
echo "============================================================"
echo "11. POST-CUTOVER HTTP BOUNDARY"
echo "============================================================"

CONTROL_HEADERS="$MANIFEST/control.headers"
INCOMPLETE_HEADERS="$MANIFEST/incomplete.headers"
DATA_HEADERS="$MANIFEST/data-plane.headers"

CONTROL_CODE="$(
    curl \
        -ksS \
        --max-time 5 \
        -D "$CONTROL_HEADERS" \
        -o /dev/null \
        -w '%{http_code}' \
        'https://davinci.icb.usp.br/c3-lims/'
)"

test "$CONTROL_CODE" = "401"

grep -qi \
    '^WWW-Authenticate:[[:space:]]*Basic' \
    "$CONTROL_HEADERS"

INCOMPLETE_CODE="$(
    curl \
        -ksS \
        --max-time 5 \
        -D "$INCOMPLETE_HEADERS" \
        -o /dev/null \
        -w '%{http_code}' \
        'https://davinci.icb.usp.br/c3-lims/internal/lab-tools/jupyter/999999999/node/gn01/65534'
)"

test "$INCOMPLETE_CODE" = "401"

grep -qi \
    '^WWW-Authenticate:[[:space:]]*Basic' \
    "$INCOMPLETE_HEADERS"

DATA_CODE="$(
    curl \
        -ksS \
        --max-time 5 \
        -D "$DATA_HEADERS" \
        -o /dev/null \
        -w '%{http_code}' \
        'https://davinci.icb.usp.br/c3-lims/internal/lab-tools/jupyter/999999999/node/gn01/65534/'
)"

test "$DATA_CODE" = "403"

if grep -qi \
    '^WWW-Authenticate:' \
    "$DATA_HEADERS"
then
    fail "Data plane unexpectedly emitted an authentication challenge."
fi

echo "control_http=$CONTROL_CODE"
echo "incomplete_tuple_http=$INCOMPLETE_CODE"
echo "data_plane_fake_http=$DATA_CODE"
echo "post_cutover_http_boundary=PASS"


echo
echo "============================================================"
echo "12. POST-CUTOVER COMPONENT VALIDATION"
echo "============================================================"

test "$(sha "$LIVE_BROKER")" = \
    "$(sha "$SOURCE_BROKER")"

test "$(sha "$LIVE_RECONCILER")" = \
    "$(sha "$SOURCE_RECONCILER")"

test "$(sha "$LIVE_SUDOERS")" = \
    "$(sha "$SOURCE_SUDOERS")"

test "$(sha "$BIOBANK_CONF")" = \
    "$(sha "$SOURCE_APACHE")"

test "$(sha "$JUPYTER_CONF")" = \
    "$(sha "$SOURCE_JUPYTER_CONF")"

test "$(sha "$JUPYTER_LUA")" = \
    "$(sha "$SOURCE_JUPYTER_LUA")"

test ! -e "$LEGACY_OOD_PROXY"

test "$(readlink -f "$CURRENT_LINK")" = \
    "$TARGET_RELEASE"

systemctl is-active --quiet \
    biobank-jupyter-proxy-reconciler.timer

httpd -t

echo "component_convergence=PASS"


echo
echo "============================================================"
echo "13. WRITE FINAL MANIFEST"
echo "============================================================"

sha256sum \
    "$BIOBANK_CONF" \
    "$JUPYTER_CONF" \
    "$JUPYTER_LUA" \
    "$LIVE_BROKER" \
    "$LIVE_RECONCILER" \
    "$LIVE_SUDOERS" \
    "$SERVICE_UNIT" \
    "$TIMER_UNIT" \
    > "$MANIFEST/after.sha256"

printf '%s\n' \
    "status=success" \
    "target_commit=$TARGET_COMMIT" \
    "current_release=$(readlink -f "$CURRENT_LINK")" \
    "static_current=$(readlink -f "$APP_ROOT/static-current")" \
    "control_http=$CONTROL_CODE" \
    "incomplete_tuple_http=$INCOMPLETE_CODE" \
    "data_plane_fake_http=$DATA_CODE" \
    "legacy_ood_proxy_present=NO" \
    "ood_portal_yml_modified=NO" \
    "ood_portal_generated_modified=NO" \
    "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    > "$MANIFEST/result.txt"

SUCCESS=1

trap - ERR INT TERM HUP

echo "deployment_manifest=$MANIFEST"
echo "independent_jupyter_cutover=PASS"
