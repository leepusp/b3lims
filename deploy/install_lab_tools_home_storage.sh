#!/usr/bin/env bash
# Install only the root-controlled helpers and sudo policy.

set -euo pipefail
umask 0077

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

test "${EUID}" -eq 0 || fail "Run this installer as root."

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="/root/biobank-lab-tools-home-storage-${STAMP}"
SHARED_RUNTIME="/home/public/biobank/runtime/notebook_server.sh"
EXPECTED_SHARED_RUNTIME_BEFORE="2e9144ff1591509eb8c8912d0ce655fac9434f7584ab217afd84f6160b2784a1"
EXPECTED_SHARED_RUNTIME_AFTER="9a576f69972add1e9a455e425964be9d4ab711fc734b66eec37fdf622f31ad0f"

test -f "$SHARED_RUNTIME" || fail "Current shared Jupyter runtime was not found."
CURRENT_SHARED_RUNTIME_SHA256="$(sha256sum "$SHARED_RUNTIME" | awk '{print $1}')"
if test "$CURRENT_SHARED_RUNTIME_SHA256" != "$EXPECTED_SHARED_RUNTIME_BEFORE" &&
   test "$CURRENT_SHARED_RUNTIME_SHA256" != "$EXPECTED_SHARED_RUNTIME_AFTER"
then
    fail "Current shared Jupyter runtime differs from the reviewed versions."
fi

bash -n \
    "$SOURCE_ROOT/sbin/biobank-user-storage" \
    "$SOURCE_ROOT/sbin/biobank-jupyter-server-runner" \
    "$SOURCE_ROOT/runtime/notebook_server.sh"
visudo -cf "$SOURCE_ROOT/sudoers/biobank-lab-tools"

install -d -m 0700 "$BACKUP_ROOT"
cp -a -- "$SHARED_RUNTIME" \
    "$BACKUP_ROOT/notebook_server.sh.shared-runtime.before"

for target in \
    /usr/local/sbin/biobank-user-storage \
    /usr/local/sbin/biobank-jupyter-server-runner \
    /etc/sudoers.d/biobank-lab-tools
do
    if test -e "$target"
    then
        cp -a -- "$target" "$BACKUP_ROOT/$(basename "$target").before"
    fi
done

install -o root -g root -m 0755 \
    "$SOURCE_ROOT/sbin/biobank-user-storage" \
    /usr/local/sbin/biobank-user-storage
install -o root -g root -m 0755 \
    "$SOURCE_ROOT/sbin/biobank-jupyter-server-runner" \
    /usr/local/sbin/biobank-jupyter-server-runner
install -o root -g biobank -m 0750 \
    "$SOURCE_ROOT/runtime/notebook_server.sh" \
    "$SHARED_RUNTIME"
install -o root -g root -m 0440 \
    "$SOURCE_ROOT/sudoers/biobank-lab-tools" \
    /etc/sudoers.d/biobank-lab-tools

visudo -cf /etc/sudoers.d/biobank-lab-tools

printf 'BIOBANK_LAB_TOOLS_HELPERS_INSTALLED backup=%s\n' "$BACKUP_ROOT"
