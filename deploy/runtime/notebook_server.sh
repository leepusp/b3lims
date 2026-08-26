#!/usr/bin/env bash
# Official Jupyter Notebook 7 server for a real user's Slurm session.

set -euo pipefail
umask 0007

ENV_ROOT="/home/public/conda/envs/biobank"
PYTHON="$ENV_ROOT/bin/python"
JUPYTER_NOTEBOOK="$ENV_ROOT/bin/jupyter-notebook"
BWRAP="/usr/bin/bwrap"

WORK_DIR="${1:-}"
RUN_DIR="${2:-}"
NOTEBOOK_NAME="${3:-notebook.ipynb}"
APP_USER="${BIOBANK_APP_USER:-}"
NOTEBOOK_ID="${BIOBANK_NOTEBOOK_ID:-}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

test -x "$PYTHON" || fail "Biobank Python environment is unavailable."
test -x "$JUPYTER_NOTEBOOK" || fail "Jupyter Notebook is unavailable."
test -x "$BWRAP" || fail "Bubblewrap is unavailable."

[[ "$APP_USER" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ ]] ||
    fail "Invalid Biobank application user."
[[ "$NOTEBOOK_ID" =~ ^[0-9]+$ ]] ||
    fail "Invalid Biobank notebook ID."
test "$(id -un)" = "$APP_USER" ||
    fail "The Slurm process does not belong to the notebook owner."

PASSWD_RECORD="$(getent passwd "$APP_USER")" ||
    fail "The notebook owner has no Unix account."
IFS=: read -r ACCOUNT_NAME _ UID_NUMBER GID_NUMBER _ USER_HOME LOGIN_SHELL \
    <<< "$PASSWD_RECORD"
test "$ACCOUNT_NAME" = "$APP_USER" || fail "Unix account mismatch."
test "$USER_HOME" = "/home/$APP_USER" ||
    fail "The notebook owner home is invalid."
test -d "$USER_HOME" && test ! -L "$USER_HOME" ||
    fail "The notebook owner home must be a real directory."

WORK_DIR="$(realpath --canonicalize-existing "$WORK_DIR")" ||
    fail "Notebook workspace does not exist."
RUN_DIR="$(realpath --canonicalize-existing "$RUN_DIR")" ||
    fail "Session runtime directory does not exist."

EXPECTED_WORK_DIR="$(
    realpath --canonicalize-existing \
        "$USER_HOME/biobank/lab_tools/jupyter/notebooks/notebook_${NOTEBOOK_ID}"
)" || fail "Expected notebook workspace does not exist."
JOB_ROOT="$(
    realpath --canonicalize-existing \
        "$USER_HOME/biobank/lab_tools/jupyter/jobs/notebook_${NOTEBOOK_ID}"
)" || fail "Expected notebook job root does not exist."

test "$WORK_DIR" = "$EXPECTED_WORK_DIR" ||
    fail "Notebook workspace does not match its owner and notebook ID."
[[ "$WORK_DIR" == "$USER_HOME/"* ]] ||
    fail "Notebook workspace is outside the authenticated user home."
WORKSPACE_RELATIVE="${WORK_DIR#"$USER_HOME/"}"
RUN_ID="${RUN_DIR#"$JOB_ROOT/"}"
[[ "$RUN_DIR" == "$JOB_ROOT/"* ]] ||
    fail "Session runtime is outside the notebook job root."
[[ "$RUN_ID" =~ ^[A-Za-z0-9_-]{1,100}$ ]] ||
    fail "Session runtime identifier is invalid."

[[ "$NOTEBOOK_NAME" =~ ^[A-Za-z0-9_.-]+\.ipynb$ ]] ||
    fail "Invalid notebook filename."
test ! -L "$WORK_DIR/$NOTEBOOK_NAME" ||
    fail "Notebook file may not be a symbolic link."

HOST="$(hostname -s)"
PORT="$(
    "$PYTHON" - <<'PY'
import socket

with socket.socket() as server:
    server.bind(("0.0.0.0", 0))
    print(server.getsockname()[1])
PY
)"
TOKEN="$(
    "$PYTHON" - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"

BASE_URL="/c3-lims/internal/lab-tools/jupyter/${NOTEBOOK_ID}/node/${HOST}/${PORT}/"
DEFAULT_URL="/tree/${WORKSPACE_RELATIVE}/${NOTEBOOK_NAME}"
CONFIG_FILE="$RUN_DIR/jupyter_server_config.py"
READY_FILE="$RUN_DIR/connection.json"
SERVER_LOG="$RUN_DIR/notebook-server.log"

mkdir -p \
    "$RUN_DIR/jupyter-runtime" \
    "$RUN_DIR/jupyter-config" \
    "$RUN_DIR/jupyter-data" \
    "$RUN_DIR/xdg-config" \
    "$RUN_DIR/xdg-data" \
    "$RUN_DIR/matplotlib" \
    "$RUN_DIR/cache" \
    "$RUN_DIR/ipython"

rm -f -- "$READY_FILE"
export CONFIG_FILE TOKEN PORT BASE_URL DEFAULT_URL USER_HOME

"$PYTHON" - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["CONFIG_FILE"])
port = int(os.environ["PORT"])
token = os.environ["TOKEN"]
base_url = os.environ["BASE_URL"]
default_url = os.environ["DEFAULT_URL"]
user_home = os.environ["USER_HOME"]

path.write_text(
    "\n".join(
        [
            "c = get_config()",
            "c.ServerApp.ip = '0.0.0.0'",
            f"c.ServerApp.port = {port!r}",
            "c.ServerApp.port_retries = 0",
            f"c.ServerApp.base_url = {base_url!r}",
            f"c.ServerApp.default_url = {default_url!r}",
            f"c.ServerApp.root_dir = {user_home!r}",
            "c.ServerApp.open_browser = False",
            "c.ServerApp.allow_remote_access = True",
            "c.ServerApp.trust_xheaders = True",
            "c.ServerApp.terminals_enabled = False",
            "c.ServerApp.disable_check_xsrf = False",
            "c.ServerApp.allow_origin = 'https://davinci.icb.usp.br'",
            f"c.IdentityProvider.token = {token!r}",
            "c.ServerApp.tornado_settings = {",
            "    'headers': {",
            "        'Content-Security-Policy': "
            "\"frame-ancestors 'self' https://davinci.icb.usp.br\",",
            "    },",
            "}",
            "",
        ]
    )
    + "\n"
)
path.chmod(0o660)
PY

touch "$SERVER_LOG"
chmod 0660 "$SERVER_LOG"
SERVER_PID=""

cleanup() {
    local return_code=$?
    trap - EXIT TERM INT

    if test -n "$SERVER_PID" && kill -0 "$SERVER_PID" 2>/dev/null
    then
        kill -TERM "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi

    rm -f -- "$READY_FILE" "$CONFIG_FILE" "$SERVER_LOG"
    rm -rf -- \
        "$RUN_DIR/jupyter-runtime" \
        "$RUN_DIR/jupyter-config" \
        "$RUN_DIR/jupyter-data" \
        "$RUN_DIR/xdg-config" \
        "$RUN_DIR/xdg-data" \
        "$RUN_DIR/matplotlib" \
        "$RUN_DIR/cache" \
        "$RUN_DIR/ipython"
    exit "$return_code"
}

trap cleanup EXIT TERM INT

/usr/bin/env -i "$BWRAP" \
    --die-with-parent \
    --new-session \
    --unshare-pid \
    --ro-bind /usr /usr \
    --symlink usr/bin /bin \
    --symlink usr/sbin /sbin \
    --symlink usr/lib /lib \
    --symlink usr/lib64 /lib64 \
    --ro-bind /etc /etc \
    --ro-bind /sys /sys \
    --proc /proc \
    --dev /dev \
    --tmpfs /tmp \
    --dir /run \
    --dir /home \
    --dir /home/public \
    --dir /home/public/conda \
    --dir /home/public/conda/envs \
    --ro-bind "$ENV_ROOT" "$ENV_ROOT" \
    --bind "$USER_HOME" "$USER_HOME" \
    --dir /workspace \
    --bind "$WORK_DIR" /workspace \
    --dir /runtime \
    --bind "$RUN_DIR" /runtime \
    --chdir "$USER_HOME" \
    --setenv HOME "$USER_HOME" \
    --setenv USER "$APP_USER" \
    --setenv LOGNAME "$APP_USER" \
    --setenv PATH "$ENV_ROOT/bin:/usr/bin:/bin" \
    --setenv JUPYTER_RUNTIME_DIR /runtime/jupyter-runtime \
    --setenv JUPYTER_CONFIG_DIR /runtime/jupyter-config \
    --setenv JUPYTER_DATA_DIR /runtime/jupyter-data \
    --setenv XDG_CONFIG_HOME /runtime/xdg-config \
    --setenv XDG_DATA_HOME /runtime/xdg-data \
    --setenv MPLCONFIGDIR /runtime/matplotlib \
    --setenv XDG_CACHE_HOME /runtime/cache \
    --setenv IPYTHONDIR /runtime/ipython \
    "$JUPYTER_NOTEBOOK" \
        --config=/runtime/jupyter_server_config.py \
        >"$SERVER_LOG" 2>&1 &

SERVER_PID=$!
READY=0

for ATTEMPT in $(seq 1 90)
do
    if ! kill -0 "$SERVER_PID" 2>/dev/null
    then
        break
    fi

    HTTP_CODE="$(
        curl \
            --silent \
            --show-error \
            --output /dev/null \
            --write-out '%{http_code}' \
            --header "Authorization: token $TOKEN" \
            "http://127.0.0.1:${PORT}${BASE_URL}api/status" \
            2>/dev/null || true
    )"

    if test "$HTTP_CODE" = "200"
    then
        READY=1
        break
    fi

    sleep 1
done

if test "$READY" != "1"
then
    printf 'ERROR: Jupyter Notebook did not become ready.\n' >&2
    tail -100 "$SERVER_LOG" >&2 || true
    exit 7
fi

export READY_FILE HOST NOTEBOOK_NAME SERVER_PID

"$PYTHON" - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ready = Path(os.environ["READY_FILE"])
temporary = ready.with_suffix(".tmp")
payload = {
    "status": "ready",
    "host": os.environ["HOST"],
    "port": int(os.environ["PORT"]),
    "base_url": os.environ["BASE_URL"],
    "default_url": os.environ["DEFAULT_URL"],
    "notebook": os.environ["NOTEBOOK_NAME"],
    "token": os.environ["TOKEN"],
    "pid": int(os.environ["SERVER_PID"]),
    "ready_at": datetime.now(timezone.utc).isoformat(),
}
temporary.write_text(json.dumps(payload, indent=2) + "\n")
temporary.chmod(0o660)
temporary.replace(ready)
ready.chmod(0o660)
PY

wait "$SERVER_PID"
