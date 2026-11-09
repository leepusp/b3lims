#!/usr/bin/env bash
# Unattended execution of a saved notebook inside a user's Slurm job.
# Same isolation as notebook_server.sh: bubblewrap, real user, no network tools.

set -euo pipefail
umask 0007

ENV_ROOT="/home/public/conda/envs/biobank"
PYTHON="$ENV_ROOT/bin/python"
BWRAP="/usr/bin/bwrap"
REPOSITORY_ROOT="/scratch/global/databases/biobank"

WORK_DIR="${1:-}"
RUN_DIR="${2:-}"
NOTEBOOK_NAME="${3:-notebook.ipynb}"
APP_USER="${BIOBANK_APP_USER:-}"
NOTEBOOK_ID="${BIOBANK_NOTEBOOK_ID:-}"
RUN_PARAMS="${BIOBANK_RUN_PARAMS:--}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

test -x "$PYTHON" || fail "Biobank Python environment is unavailable."
test -x "$BWRAP" || fail "Bubblewrap is unavailable."

[[ "$APP_USER" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ ]] ||
    fail "Invalid Biobank application user."
[[ "$NOTEBOOK_ID" =~ ^[0-9]+$ ]] || fail "Invalid Biobank notebook ID."
[[ "$RUN_PARAMS" == "-" || "$RUN_PARAMS" =~ ^[A-Za-z0-9+/=]{1,12000}$ ]] ||
    fail "Invalid run parameters."
test "$(id -un)" = "$APP_USER" ||
    fail "The Slurm process does not belong to the notebook owner."

PASSWD_RECORD="$(getent passwd "$APP_USER")" ||
    fail "The notebook owner has no Unix account."
IFS=: read -r ACCOUNT_NAME _ _ _ _ USER_HOME _ <<< "$PASSWD_RECORD"
test "$ACCOUNT_NAME" = "$APP_USER" || fail "Unix account mismatch."
test "$USER_HOME" = "/home/$APP_USER" || fail "The notebook owner home is invalid."
test -d "$USER_HOME" && test ! -L "$USER_HOME" ||
    fail "The notebook owner home must be a real directory."

WORK_DIR="$(realpath --canonicalize-existing "$WORK_DIR")" ||
    fail "Notebook workspace does not exist."
RUN_DIR="$(realpath --canonicalize-existing "$RUN_DIR")" ||
    fail "Run directory does not exist."
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
[[ "$RUN_DIR" == "$JOB_ROOT/"* ]] || fail "Run directory is outside the job root."
[[ "$NOTEBOOK_NAME" =~ ^[A-Za-z0-9_.-]+\.ipynb$ ]] || fail "Invalid notebook filename."
test -f "$WORK_DIR/$NOTEBOOK_NAME" && test ! -L "$WORK_DIR/$NOTEBOOK_NAME" ||
    fail "Notebook file was not found."

mkdir -p "$RUN_DIR/xdg-config" "$RUN_DIR/xdg-data" "$RUN_DIR/matplotlib" \
    "$RUN_DIR/cache" "$RUN_DIR/ipython" "$RUN_DIR/jupyter-runtime"
rm -f -- "$RUN_DIR/result.json" "$RUN_DIR/executed.ipynb" "$RUN_DIR/outputs.json"

# The repository is mounted read-only when it exists, so b3repo works in the notebook.
REPOSITORY_ARGS=()
if test -d "$REPOSITORY_ROOT"
then
    REPOSITORY_ARGS=(
        --dir /scratch
        --dir /scratch/global
        --dir /scratch/global/databases
        --ro-bind "$REPOSITORY_ROOT" "$REPOSITORY_ROOT"
    )
fi

cleanup() {
    rm -rf -- "$RUN_DIR/xdg-config" "$RUN_DIR/xdg-data" "$RUN_DIR/matplotlib" \
        "$RUN_DIR/cache" "$RUN_DIR/ipython" "$RUN_DIR/jupyter-runtime"
}
trap cleanup EXIT

# The executor writes /runtime/result.json even when the notebook fails.
set +e
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
    "${REPOSITORY_ARGS[@]}" \
    --bind "$USER_HOME" "$USER_HOME" \
    --dir /workspace \
    --bind "$WORK_DIR" /workspace \
    --dir /runtime \
    --bind "$RUN_DIR" /runtime \
    --chdir /workspace \
    --setenv HOME "$USER_HOME" \
    --setenv USER "$APP_USER" \
    --setenv LOGNAME "$APP_USER" \
    --setenv PATH "$ENV_ROOT/bin:/usr/bin:/bin" \
    --setenv JUPYTER_RUNTIME_DIR /runtime/jupyter-runtime \
    --setenv XDG_CONFIG_HOME /runtime/xdg-config \
    --setenv XDG_DATA_HOME /runtime/xdg-data \
    --setenv MPLCONFIGDIR /runtime/matplotlib \
    --setenv XDG_CACHE_HOME /runtime/cache \
    --setenv IPYTHONDIR /runtime/ipython \
    --setenv BIOBANK_RUN_PARAMS "$RUN_PARAMS" \
    --setenv BIOBANK_RUN_NOTEBOOK "/workspace/$NOTEBOOK_NAME" \
    "$PYTHON" - >"$RUN_DIR/run.log" 2>&1 <<'PY'
import base64
import json
import os
import re
import sys
import time

RESULT = "/runtime/result.json"
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")


def finish(status, **extra):
    payload = {"status": status, **extra}
    with open(RESULT, "w") as handle:
        json.dump(payload, handle)
    sys.exit(0 if status == "completed" else 1)


started = time.time()

try:
    import nbformat
    from nbclient import NotebookClient
except ImportError as exc:
    finish("failed", error=f"Missing package: {exc.name}")

params = {}
raw = os.environ.get("BIOBANK_RUN_PARAMS", "-")

if raw != "-":
    try:
        params = json.loads(base64.b64decode(raw).decode("utf-8"))
        assert isinstance(params, dict) and len(params) <= 20
        assert all(KEY.match(k) and isinstance(v, str) and len(v) <= 200 for k, v in params.items())
    except Exception:
        finish("failed", error="Invalid run parameters.")

try:
    notebook = nbformat.read(os.environ["BIOBANK_RUN_NOTEBOOK"], as_version=4)
except Exception as exc:
    finish("failed", error=f"Could not read notebook: {str(exc)[:200]}")

if params:
    source = "# Parameters injected by Biobank\n" + "\n".join(f"{k} = {v!r}" for k, v in params.items())
    cell = nbformat.v4.new_code_cell(source)
    cell.metadata["tags"] = ["injected-parameters"]
    notebook.cells.insert(0, cell)

code_cells = sum(1 for c in notebook.cells if c.cell_type == "code")
error = ""

try:
    NotebookClient(notebook, timeout=None, kernel_name="python3", resources={"metadata": {"path": "/workspace"}}).execute()
except Exception as exc:
    error = f"{type(exc).__name__}: {str(exc)[:400]}"

executed = sum(1 for c in notebook.cells if c.cell_type == "code" and c.get("execution_count"))


def collect_outputs(cells):
    """Text and PNG figures of each code cell, small enough to show on a card."""
    collected, images, image_chars = [], 0, 0

    for index, cell in enumerate(cells):
        if cell.cell_type != "code":
            continue

        text, pngs = [], []

        for output in cell.get("outputs", []):
            kind = output.get("output_type")
            data = output.get("data", {})

            if kind == "stream":
                text.append(str(output.get("text", "")))
            elif kind in ("execute_result", "display_data"):
                if "text/plain" in data and "image/png" not in data:
                    text.append(str(data["text/plain"]))

                png = data.get("image/png")

                if isinstance(png, str):
                    png = png.replace("\n", "")

                    if images < 6 and len(png) <= 400000 and image_chars + len(png) <= 1500000:
                        pngs.append(png)
                        images += 1
                        image_chars += len(png)
            elif kind == "error":
                text.append(str(output.get("ename", "")) + ": " + str(output.get("evalue", "")))

        if text or pngs:
            collected.append({"cell": index, "text": "".join(text)[:1500], "images": pngs})

        if len(collected) >= 30:
            break

    return {"cells": collected}


try:
    with open("/runtime/outputs.json", "w") as handle:
        json.dump(collect_outputs(notebook.cells), handle)
except Exception:
    pass

try:
    nbformat.write(notebook, "/runtime/executed.ipynb")
except Exception:
    pass

if error:
    finish("failed", error=error, cells=code_cells, executed=executed, seconds=round(time.time() - started, 1))

finish("completed", cells=code_cells, executed=executed, seconds=round(time.time() - started, 1))
PY
STATUS=$?
set -e

if test ! -f "$RUN_DIR/result.json"
then
    printf '{"status":"failed","error":"Runner exited with code %s."}\n' "$STATUS" >"$RUN_DIR/result.json"
fi

exit "$STATUS"
