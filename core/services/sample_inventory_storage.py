import csv
import hashlib
import json
import mimetypes
import re
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db.models import ForeignKey
from django.utils import timezone

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile


def safe_name(value, fallback="unnamed"):
    value = str(value or "").strip()
    if not value:
        value = fallback
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    return value or fallback


def as_json_value(value):
    if value is None:
        return None

    if isinstance(value, UUID):
        return str(value)

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def get_inventory_root():
    return Path(settings.BIOBANK_INVENTORY_ROOT)


def get_sample_inventory_root():
    return get_inventory_root() / "samples"


def get_sample_workspace(sample):
    sample_id = getattr(sample, "sample_id", "") or f"sample_{sample.id}"
    return get_sample_inventory_root() / safe_name(sample_id)


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)

    return digest.hexdigest()


def serialize_sample(sample):
    payload = {}

    for field in sample._meta.fields:
        name = field.name
        value = getattr(sample, name)

        if isinstance(field, ForeignKey):
            if value is None:
                payload[name] = None
            else:
                payload[name] = {
                    "id": getattr(value, "id", None),
                    "label": str(value),
                }
        else:
            payload[name] = as_json_value(value)

    return payload


def serialize_sample_file(sample_file, compute_checksum=True):
    relative_path = str(sample_file.file.name)
    absolute_path = ""

    try:
        absolute_path = sample_file.file.path
    except Exception:
        absolute_path = str(Path(settings.MEDIA_ROOT) / relative_path)

    path = Path(absolute_path)
    exists = path.exists() and path.is_file()

    sha256 = ""
    if compute_checksum and exists:
        sha256 = sha256_file(path)

    return {
        "id": sample_file.id,
        "relative_path": relative_path,
        "absolute_path": absolute_path,
        "exists": exists,
        "description": sample_file.description,
        "mime_type": sample_file.mime_type,
        "file_size": sample_file.file_size,
        "category": sample_file.category,
        "uploaded_at": sample_file.uploaded_at.isoformat() if sample_file.uploaded_at else "",
        "sha256": sha256,
    }


def find_exact_media_matches_for_sample(sample, compute_checksums=False):
    """
    Finds current MEDIA_ROOT files that directly contain the sample_id token.

    This is intentionally conservative. Existing files under data/_unassigned_samples
    may not match current sample_id values, so they remain indexed globally but are
    not automatically assigned to a sample.
    """
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return []

    sample_id = str(getattr(sample, "sample_id", "") or "").casefold()
    sample_token = safe_name(sample_id).casefold()

    if not sample_id:
        return []

    matches = []

    for path in media_root.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(media_root).as_posix()
        rel_fold = rel.casefold()

        if sample_id in rel_fold or sample_token in rel_fold:
            item = {
                "relative_path": rel,
                "absolute_path": str(path),
                "size_bytes": path.stat().st_size,
                "modified_at": timezone.datetime.fromtimestamp(
                    path.stat().st_mtime,
                    tz=timezone.get_current_timezone(),
                ).isoformat(),
                "mime_type": mimetypes.guess_type(path.name)[0],
            }

            if compute_checksums:
                item["sha256"] = sha256_file(path)

            matches.append(item)

    return matches


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path


def write_sample_manifest(sample, compute_file_checksums=False):
    workspace = get_sample_workspace(sample)
    workspace.mkdir(parents=True, exist_ok=True)

    for subdir in ["attachments", "exports"]:
        (workspace / subdir).mkdir(parents=True, exist_ok=True)

    media_matches = find_exact_media_matches_for_sample(
        sample,
        compute_checksums=compute_file_checksums,
    )

    curated_files = [
        serialize_sample_file(sample_file, compute_checksum=compute_file_checksums)
        for sample_file in sample.files.all().order_by("category", "file", "id")
    ]

    manifest = {
        "schema": "biobank.sample_manifest.v1",
        "sample": serialize_sample(sample),
        "workspace": str(workspace),
        "media_matches": media_matches,
        "media_match_count": len(media_matches),
        "curated_files": curated_files,
        "curated_file_count": len(curated_files),
        "generated_at": timezone.now().isoformat(),
    }

    manifest_path = workspace / "sample_manifest.json"
    write_json(manifest_path, manifest)

    return {
        "sample_id": sample.sample_id,
        "sample_pk": sample.id,
        "workspace": str(workspace),
        "manifest_path": str(manifest_path),
        "media_match_count": len(media_matches),
        "curated_file_count": len(curated_files),
    }


def sample_index_row(sample, manifest_info):
    def rel_label(name):
        obj = getattr(sample, name, None)
        if obj is None:
            return ""
        return str(obj)

    return {
        "id": sample.id,
        "uuid": str(sample.uuid),
        "sample_id": sample.sample_id,
        "sample_type": sample.sample_type,
        "organism_name": sample.organism_name,
        "status": sample.status,
        "biobank": rel_label("biobank"),
        "owner": rel_label("owner"),
        "research_group": rel_label("research_group"),
        "is_public": sample.is_public,
        "is_active": sample.is_active,
        "storage_location": sample.storage_location,
        "created_at": sample.created_at.isoformat() if sample.created_at else "",
        "updated_at": sample.updated_at.isoformat() if sample.updated_at else "",
        "manifest_path": manifest_info["manifest_path"],
        "media_match_count": manifest_info["media_match_count"],
        "curated_file_count": manifest_info["curated_file_count"],
    }


def write_samples_index(rows):
    root = get_inventory_root()
    root.mkdir(parents=True, exist_ok=True)

    json_path = root / "samples_index.json"
    tsv_path = root / "samples_index.tsv"

    write_json(json_path, rows)

    fieldnames = [
        "id",
        "uuid",
        "sample_id",
        "sample_type",
        "organism_name",
        "status",
        "biobank",
        "owner",
        "research_group",
        "is_public",
        "is_active",
        "storage_location",
        "created_at",
        "updated_at",
        "manifest_path",
        "media_match_count",
        "curated_file_count",
    ]

    with tsv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    return {
        "json_path": str(json_path),
        "tsv_path": str(tsv_path),
    }


def write_media_files_index(compute_checksums=True):
    """
    Index all files currently stored under MEDIA_ROOT.

    This preserves traceability of existing uploaded data without moving files.
    """
    media_root = Path(settings.MEDIA_ROOT)
    root = get_inventory_root()
    root.mkdir(parents=True, exist_ok=True)

    out_path = root / "media_files_index.tsv"

    fieldnames = [
        "relative_path",
        "absolute_path",
        "size_bytes",
        "modified_at",
        "mime_type",
        "sha256",
    ]

    rows = []

    if media_root.exists():
        for path in sorted(media_root.rglob("*")):
            if not path.is_file():
                continue

            stat = path.stat()
            row = {
                "relative_path": path.relative_to(media_root).as_posix(),
                "absolute_path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": timezone.datetime.fromtimestamp(
                    stat.st_mtime,
                    tz=timezone.get_current_timezone(),
                ).isoformat(),
                "mime_type": mimetypes.guess_type(path.name)[0] or "",
                "sha256": sha256_file(path) if compute_checksums else "",
            }
            rows.append(row)

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    return {
        "path": str(out_path),
        "file_count": len(rows),
    }


def sync_all_sample_inventory(compute_file_checksums=True):
    get_sample_inventory_root().mkdir(parents=True, exist_ok=True)

    rows = []
    sample_results = []

    for sample in Sample.objects.all().order_by("sample_id", "id"):
        manifest_info = write_sample_manifest(
            sample,
            compute_file_checksums=compute_file_checksums,
        )
        sample_results.append(manifest_info)
        rows.append(sample_index_row(sample, manifest_info))

    index_info = write_samples_index(rows)
    media_info = write_media_files_index(compute_checksums=compute_file_checksums)

    return {
        "sample_count": len(sample_results),
        "sample_manifests": sample_results,
        "samples_index": index_info,
        "media_files_index": media_info,
        "generated_at": timezone.now().isoformat(),
    }
