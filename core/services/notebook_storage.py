import csv
import json
import os
import pwd
import re
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def safe_name(value, fallback="unnamed"):
    value = str(value or "").strip()
    if not value:
        value = fallback
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    return value or fallback


def get_username(user):
    try:
        return safe_name(user.get_username(), fallback=f"user_{user.id}")
    except Exception:
        return "unknown_user"


def get_home_for_username(username):
    """
    Resolve the Linux home directory for the Django username.

    For DaVinci usage, the Django username should match the Unix account,
    for example: ccalomeno -> /home/ccalomeno.
    """
    username = safe_name(username)

    try:
        home = Path(pwd.getpwnam(username).pw_dir)
    except KeyError as exc:
        raise RuntimeError(
            f"No Linux account/home directory found for Django username '{username}'. "
            "For DaVinci notebook storage, create/use a Django user whose username "
            "matches the Unix account, for example 'ccalomeno'."
        ) from exc

    if not home.exists():
        raise RuntimeError(f"Resolved home directory does not exist: {home}")

    return home


def get_notebook_root_for_user(user):
    username = get_username(user)

    mode = getattr(settings, "BIOBANK_NOTEBOOK_STORAGE_MODE", "home")

    if mode == "public":
        public_root = Path(
            getattr(settings, "BIOBANK_NOTEBOOK_ROOT", "/home/public/biobank/users")
        )
        return public_root / username / "notebooks"

    # Default for DaVinci user-level testing:
    # /home/<username>/biobank_notebooks/
    return get_home_for_username(username) / "biobank_notebooks"


def get_entry_workspace(entry):
    return get_notebook_root_for_user(entry.author) / f"entry_{entry.id}"


def ensure_entry_workspace(entry):
    workspace = get_entry_workspace(entry)

    for subdir in [
        "",
        "attachments",
        "tables",
        
        "sequences",
        "plasmids",
        
        "results",
        "manifests",
    ]:
        (workspace / subdir).mkdir(parents=True, exist_ok=True)

    return workspace


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path


def clean_sequence(value):
    lines = []
    for line in str(value or "").splitlines():
        if line.startswith(">"):
            continue
        lines.append(line.strip())
    return re.sub(r"\s+", "", "".join(lines)).upper()


def fasta_wrap(sequence, width=80):
    return "\n".join(sequence[i:i + width] for i in range(0, len(sequence), width))


def write_table_block(block, workspace):
    data = block.content_data or {}
    table = data.get("content") or []
    raw = data.get("raw") or ""

    base = f"block_{block.id}_{safe_name(block.title, 'table')}"

    raw_path = workspace / "tables" / f"{base}.txt"
    csv_path = workspace / "tables" / f"{base}.csv"

    raw_path.write_text(raw, encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if table:
            writer.writerows(table)

    return {
        "raw_path": str(raw_path),
        "csv_path": str(csv_path),
    }


def write_code_block(block, workspace):
    data = block.content_data or {}
    code = data.get("code") or ""

    path = workspace / "code" / f"block_{block.id}_{safe_name(block.title, 'analysis')}.py"
    path.write_text(code, encoding="utf-8")

    return {"code_path": str(path)}


def write_sequence_block(block, workspace, subdir="sequences", default_type="sequence"):
    data = block.content_data or {}

    name = data.get("name") or block.title or f"block_{block.id}"
    sequence_type = data.get("sequence_type") or default_type
    topology = data.get("topology") or ""
    sequence = clean_sequence(data.get("sequence") or "")

    path = workspace / subdir / f"block_{block.id}_{safe_name(name)}.fasta"

    header = f">{safe_name(name)} type={sequence_type}"
    if topology:
        header += f" topology={topology}"

    text = header + "\n"
    text += fasta_wrap(sequence) + "\n" if sequence else "\n"

    path.write_text(text, encoding="utf-8")

    return {
        "fasta_path": str(path),
        "length": len(sequence),
    }


def write_slurm_block(block, workspace):
    data = block.content_data or {}

    workdir = workspace / "s" / f"block_{block.id}_{safe_name(block.title, '')}"
    workdir.mkdir(parents=True, exist_ok=True)

    command_path = workdir / "command.txt"
    command_path.write_text(data.get("command") or "", encoding="utf-8")

    return {
        "slurm_workdir": str(workdir),
        "command_path": str(command_path),
    }


def write_block_artifact(block, workspace):
    if block.block_type == "table":
        return write_table_block(block, workspace)

        return write_code_block(block, workspace)

    if block.block_type == "sequence":
        return write_sequence_block(block, workspace, "sequences", "sequence")

    if block.block_type == "plasmid":
        return write_sequence_block(block, workspace, "plasmids", "plasmid")

        return write_slurm_block(block, workspace)

    return {}


def build_entry_manifest(entry, workspace, artifacts):
    samples = []
    for link in entry.sample_links.select_related("sample").all():
        samples.append(
            {
                "link_id": link.id,
                "sample_pk": link.sample_id,
                "sample_id": getattr(link.sample, "sample_id", ""),
                "linked_at": link.linked_at,
                "snapshot": link.snapshot_json,
            }
        )

    blocks = []
    for block in entry.blocks.all():
        blocks.append(
            {
                "id": block.id,
                "type": block.block_type,
                "title": block.title,
                "order": block.order,
                "updated_at": block.updated_at,
            }
        )

    attachments = []
    for attachment in entry.attachments.all():
        attachments.append(
            {
                "id": attachment.id,
                "file": attachment.file.name,
                "caption": attachment.caption,
                "attachment_type": attachment.attachment_type,
                "checksum_sha256": attachment.checksum_sha256,
                "created_at": attachment.created_at,
            }
        )

    return {
        "entry": {
            "id": entry.id,
            "title": entry.title,
            "author": entry.author.get_username(),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "workspace": str(workspace),
        },
        "samples": samples,
        "blocks": blocks,
        "attachments": attachments,
        "artifacts": artifacts,
        "generated_at": timezone.now(),
    }


def sync_entry_workspace(entry):
    workspace = ensure_entry_workspace(entry)

    artifacts = {}
    for block in entry.blocks.all():
        artifacts[str(block.id)] = write_block_artifact(block, workspace)

    manifest = build_entry_manifest(entry, workspace, artifacts)
    manifest_path = workspace / "entry_manifest.json"
    write_json(manifest_path, manifest)

    return {
        "workspace": str(workspace),
        "manifest_path": str(manifest_path),
        "artifacts": artifacts,
    }
