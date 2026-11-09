#!/usr/bin/env bash
# Install the unattended-notebook runtime (broker run-* actions, notebook_run.sh,
# repository bind in notebook_server.sh). Manual, root only.
#
#   install_notebook_batch_runtime.sh --check  REPO BASE_COMMIT
#   install_notebook_batch_runtime.sh --install REPO BASE_COMMIT
#
# BASE_COMMIT is the commit those files were last installed from (the live one
# before p82). The live files must match it, otherwise somebody changed them by
# hand and nothing is touched.
set -euo pipefail

MODE="${1:-}"
REPO="${2:-}"
BASE="${3:-}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

test "$(id -u)" = 0 || fail "Run as root."
[[ "$MODE" == "--check" || "$MODE" == "--install" ]] || fail "Usage: $0 --check|--install REPO BASE_COMMIT"
test -d "$REPO/.git" || fail "REPO is not a git checkout."
[[ "$BASE" =~ ^[0-9a-f]{40}$ ]] || fail "BASE_COMMIT must be a full commit hash."

GIT=(git -c safe.directory="$REPO" -C "$REPO")
RUNTIME_ROOT="/home/public/apps/biobank/runtime"
LIVE_BROKER="/usr/local/sbin/biobank-jupyter-server-broker"
LIVE_SERVER="$RUNTIME_ROOT/notebook_server.sh"
LIVE_RUN="$RUNTIME_ROOT/notebook_run.sh"
SRC_BROKER="$REPO/deploy/sbin/biobank-jupyter-server-broker"
SRC_SERVER="$REPO/deploy/runtime/notebook_server.sh"
SRC_RUN="$REPO/deploy/runtime/notebook_run.sh"

test -z "$("${GIT[@]}" status --porcelain -- deploy)" || fail "Uncommitted changes under deploy/."

same_as_base() { # live_file repo_path
    local live="$1" path="$2"
    test "$(sha256sum <"$live" | cut -d' ' -f1)" = "$("${GIT[@]}" show "$BASE:$path" | sha256sum | cut -d' ' -f1)"
}

echo "== drift check against $BASE =="
same_as_base "$LIVE_BROKER" deploy/sbin/biobank-jupyter-server-broker || fail "Live broker differs from BASE_COMMIT."
same_as_base "$LIVE_SERVER" deploy/runtime/notebook_server.sh || fail "Live notebook_server.sh differs from BASE_COMMIT."
echo "live files match BASE_COMMIT"

echo "== syntax =="
for f in "$SRC_BROKER" "$SRC_SERVER" "$SRC_RUN"; do bash -n "$f"; done
echo "bash -n OK"

echo "== diff to be installed =="
diff -u "$LIVE_BROKER" "$SRC_BROKER" | diffstat 2>/dev/null || diff -u "$LIVE_BROKER" "$SRC_BROKER" | grep -c '^[+-]' || true

if test "$MODE" = "--check"
then
    echo "check=PASS (nothing modified)"
    exit 0
fi

BACKUP="/root/backups/notebook-batch-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -p "$LIVE_BROKER" "$BACKUP/biobank-jupyter-server-broker"
cp -p "$LIVE_SERVER" "$BACKUP/notebook_server.sh"
test ! -e "$LIVE_RUN" || cp -p "$LIVE_RUN" "$BACKUP/notebook_run.sh"

SERVER_OWNER="$(stat -c '%u:%g' "$LIVE_SERVER")"
SERVER_MODE="$(stat -c '%a' "$LIVE_SERVER")"

install -o root -g root -m 0755 "$SRC_BROKER" "$LIVE_BROKER.new"
install -o "${SERVER_OWNER%%:*}" -g "${SERVER_OWNER##*:}" -m "$SERVER_MODE" "$SRC_SERVER" "$LIVE_SERVER.new"
install -o "${SERVER_OWNER%%:*}" -g "${SERVER_OWNER##*:}" -m "$SERVER_MODE" "$SRC_RUN" "$LIVE_RUN.new"
mv -f "$LIVE_RUN.new" "$LIVE_RUN"
mv -f "$LIVE_SERVER.new" "$LIVE_SERVER"
mv -f "$LIVE_BROKER.new" "$LIVE_BROKER"

bash -n "$LIVE_BROKER" && bash -n "$LIVE_SERVER" && bash -n "$LIVE_RUN"

cat <<MSG
install=PASS
backup=$BACKUP
rollback:
  install -o root -g root -m 0755 $BACKUP/biobank-jupyter-server-broker $LIVE_BROKER
  install -m $SERVER_MODE $BACKUP/notebook_server.sh $LIVE_SERVER
  rm -f $LIVE_RUN
MSG
