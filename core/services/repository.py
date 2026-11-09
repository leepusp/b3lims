"""Internal data repository: build a package's files and publish them to disk.

Layout under ``settings.BIOBANK_REPOSITORY_ROOT`` (``/scratch/global/databases/biobank``)::

    packages/<year>/<id>-<slug>/
        manifest.json            what is inside, who approved, taxon and lineage
        ro-crate-metadata.json   RO-Crate 1.1 description of the same files
        sequences/*.fasta  structures/*  samples.tsv  entries/*.html
    index/packages.jsonl         one line per published package (for Jupyter/Galaxy)
    index/taxonomy.sqlite        local NCBI taxonomy (see taxonomy_local)

Published packages are never overwritten.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models.lab_tools.submission import SubmissionPackage
from core.services import taxonomy_local

SCHEMA = "b3-lims-package/1"
LICENSE_DEFAULT = "https://creativecommons.org/licenses/by/4.0/"
MAX_ITEMS = 500
MAX_STRUCTURE_BYTES = 200 * 1024 * 1024


def repository_root() -> Path:
    return Path(getattr(settings, "BIOBANK_REPOSITORY_ROOT", "/scratch/global/databases/biobank"))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:50] or "package"


def safe_name(text: str, fallback: str = "file") -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (text or "").strip()).strip("._")[:100] or fallback


def package_relpath(package: SubmissionPackage) -> str:
    year = (package.approved_at or timezone.now()).year

    return f"packages/{year}/{package.pk}-{slugify(package.title)}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fasta(name: str, kind: str, topology: str, description: str, sequence: str) -> bytes:
    header = f">{safe_name(name, 'record')} type={kind} topology={topology or 'linear'}"

    if description:
        header += " " + " ".join(description.split())[:200]

    body = "\n".join(sequence[i:i + 70] for i in range(0, len(sequence), 70))

    return f"{header}\n{body}\n".encode()


def _read_structure(structure) -> bytes | None:
    try:
        with structure.file.open("rb") as handle:
            return handle.read(MAX_STRUCTURE_BYTES + 1)[:MAX_STRUCTURE_BYTES]
    except Exception:  # noqa: BLE001 - storage may be unreachable; the manifest records it
        return None


def collect_files(package: SubmissionPackage) -> tuple[dict[str, bytes], list[dict]]:
    """Files to write (relative path -> bytes) and a description of every item."""
    files: dict[str, bytes] = {}
    described: list[dict] = []
    samples: list = []
    used: set[str] = set()

    def unique(path: str) -> str:
        base, dot, ext = path.rpartition(".")
        candidate, n = path, 1

        while candidate in used:
            n += 1
            candidate = f"{base}-{n}{dot}{ext}" if dot else f"{path}-{n}"

        used.add(candidate)

        return candidate

    for item in package.items.select_related("molecule", "structure", "structure__molecule", "sample", "entry"):
        info = {"kind": item.kind, "label": item.label, "files": []}

        if item.kind == "sequence" and item.molecule:
            m = item.molecule
            path = unique(f"sequences/{safe_name(m.name, 'sequence')}.fasta")

            files[path] = _fasta(m.name, m.sequence_type, m.topology, m.description, (m.sequence or "").upper())
            info.update(record_id=m.pk, sequence_type=m.sequence_type, length=m.length, files=[path])
        elif item.kind == "structure" and item.structure:
            s = item.structure
            data = _read_structure(s)

            if data is None:
                info["warning"] = "structure file could not be read"
            else:
                path = unique(f"structures/{safe_name(s.original_filename, 'structure')}")

                files[path] = data
                info.update(record_id=s.pk, molecule=s.molecule.name, source_format=s.source_format, files=[path])
        elif item.kind == "sample" and item.sample:
            samples.append(item.sample)
            info.update(record_id=item.sample.pk, sample_id=item.sample.sample_id)
        elif item.kind == "entry" and item.entry:
            e = item.entry
            path = unique(f"entries/{e.pk}-{safe_name(e.title, 'entry')}.html")
            page = f"<!doctype html><meta charset='utf-8'><title>{_esc(e.title)}</title><h1>{_esc(e.title)}</h1>\n{e.content or ''}\n"

            files[path] = page.encode()
            info.update(record_id=e.pk, files=[path])
        else:
            info["warning"] = "the source record no longer exists"

        described.append(info)

    if samples:
        out = io.StringIO()
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")

        writer.writerow(["sample_id", "sample_type", "organism_name"])

        for s in samples:
            writer.writerow([s.sample_id, s.sample_type or "", s.organism_name or ""])

        files["samples.tsv"] = out.getvalue().encode()

        for info in described:
            if info["kind"] == "sample" and "warning" not in info:
                info["files"] = ["samples.tsv"]

    return files, described


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _taxon_block(package: SubmissionPackage) -> dict | None:
    if not package.taxon_id:
        return None

    return {
        "ncbi_taxid": package.taxon_id,
        "name": package.taxon_name,
        "taxonomy_version": package.taxonomy_version,
        "lineage": package.lineage,
        "lineage_ids": [str(x.get("taxid")) for x in package.lineage],
    }


def build_manifest(package: SubmissionPackage, described: list[dict], files: dict[str, bytes]) -> dict:
    return {
        "schema": SCHEMA,
        "id": package.pk,
        "title": package.title,
        "description": package.description,
        "destination": package.destination,
        "owner": package.owner.get_username(),
        "created_at": package.created_at.isoformat(timespec="seconds"),
        "proposed_at": package.proposed_at.isoformat(timespec="seconds") if package.proposed_at else None,
        "approval": {
            "approved_by": package.approved_by.get_username() if package.approved_by else None,
            "approved_at": package.approved_at.isoformat(timespec="seconds") if package.approved_at else None,
            "note": package.review_note,
        },
        "taxon": _taxon_block(package),
        "metadata": package.metadata,
        "workflow": {"id": package.workflow_id, "name": package.workflow.name} if package.workflow_id else None,
        "items": described,
        "files": [{"path": p, "bytes": len(b), "sha256": _sha256(b)} for p, b in sorted(files.items())],
    }


def build_rocrate(package: SubmissionPackage, manifest: dict) -> dict:
    meta = package.metadata or {}
    graph = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": package.title,
            "description": package.description or package.title,
            "datePublished": (package.approved_at or timezone.now()).date().isoformat(),
            "license": {"@id": meta.get("license") or LICENSE_DEFAULT},
            "creator": {"@id": f"#{package.owner.get_username()}"},
            "hasPart": [{"@id": f["path"]} for f in manifest["files"]] + [{"@id": "manifest.json"}],
        },
        {"@id": f"#{package.owner.get_username()}", "@type": "Person", "name": package.owner.get_username()},
        {"@id": "manifest.json", "@type": "File", "encodingFormat": "application/json", "name": "Package manifest"},
    ]

    if package.taxon_id:
        taxon_ref = {"@id": f"https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={package.taxon_id}"}

        graph[1]["about"] = taxon_ref
        graph.append({**taxon_ref, "@type": "Taxon", "name": package.taxon_name, "taxonRank": (package.lineage[-1].get("rank") if package.lineage else "")})

    for f in manifest["files"]:
        graph.append({"@id": f["path"], "@type": "File", "name": Path(f["path"]).name, "contentSize": f["bytes"], "sha256": f["sha256"]})

    return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}


# --- taxon ---------------------------------------------------------------------


def set_taxon(package: SubmissionPackage, taxid) -> None:
    """Freeze a taxon and its lineage from the local taxonomy on the package."""
    taxid = str(taxid or "").strip()

    if not taxid:
        package.taxon_id = package.taxon_name = package.taxonomy_version = ""
        package.lineage = []

        return

    if not taxid.isdigit():
        raise ValidationError("The taxon must be an NCBI taxonomy id (a number).")

    chain = taxonomy_local.lineage(taxid)

    if not chain:
        if taxonomy_local.available():
            raise ValidationError(f"Taxon {taxid} was not found in the local taxonomy.")

        raise ValidationError("The local taxonomy index is not built yet; ask an administrator to run build_taxonomy_index.")

    package.taxon_id = taxid
    package.taxon_name = chain[-1]["name"]
    package.taxonomy_version = taxonomy_local.version()
    package.lineage = chain


# --- publishing ----------------------------------------------------------------


def _write_tree(base: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        target = (base / rel).resolve()

        if base.resolve() not in target.parents:
            raise ValidationError("Refusing to write outside the package directory.")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def publish_internal(package: SubmissionPackage) -> str:
    """Write an approved package to the internal repository. Returns its relative path."""
    if package.status != SubmissionPackage.Status.APPROVED:
        raise ValidationError("Only approved packages can be published.")
    if package.destination != SubmissionPackage.Destination.INTERNAL:
        raise ValidationError("This destination is not available yet; only the internal repository is.")

    root = repository_root()

    if not root.is_dir():
        raise ValidationError(f"The repository directory {root} does not exist or is not reachable.")

    rel = package_relpath(package)
    final = root / rel

    if final.exists():
        raise ValidationError("This package already exists in the repository.")

    files, described = collect_files(package)
    manifest = build_manifest(package, described, files)
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()

    files["manifest.json"] = manifest_bytes
    files["ro-crate-metadata.json"] = (json.dumps(build_rocrate(package, manifest), indent=2, ensure_ascii=False) + "\n").encode()

    final.parent.mkdir(parents=True, exist_ok=True)

    staging = final.parent / f".{final.name}.staging-{os.getpid()}"

    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()

    try:
        _write_tree(staging, files)
        os.rename(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    try:
        for path in [final, *final.rglob("*")]:
            os.chmod(path, 0o2775 if path.is_dir() else 0o664)
    except OSError:
        pass

    package.repository_path = rel
    package.manifest_sha256 = _sha256(manifest_bytes)
    package.published_at = timezone.now()
    package.status = SubmissionPackage.Status.PUBLISHED
    package.save(update_fields=["repository_path", "manifest_sha256", "published_at", "status", "updated_at"])
    _append_index(root, package, manifest)

    return rel


def _append_index(root: Path, package: SubmissionPackage, manifest: dict) -> None:
    """One JSON line per published package, for tools that do not run Django."""
    line = {
        "id": package.pk, "title": package.title, "path": package.repository_path,
        "taxon_id": package.taxon_id, "taxon_name": package.taxon_name,
        "lineage_ids": [str(x.get("taxid")) for x in package.lineage],
        "published_at": package.published_at.isoformat(timespec="seconds"),
        "owner": package.owner.get_username(), "files": len(manifest["files"]),
        "manifest_sha256": package.manifest_sha256,
    }

    try:
        index = root / "index"

        index.mkdir(exist_ok=True)

        with open(index / "packages.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
