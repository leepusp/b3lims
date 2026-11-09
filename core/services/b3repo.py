"""b3repo: read the B3 LIMS internal repository from a Jupyter notebook or a Galaxy tool.

Standard library only (no Django), so it can be imported on any DaVinci node::

    import sys; sys.path.insert(0, "/scratch/global/databases/biobank/lib")
    import b3repo

    b3repo.find(q="GFP")                      # published packages by title
    b3repo.find(taxid=1239)                   # packages whose taxon lies under Bacillota
    b3repo.search_taxa("Staphylococcus a")    # NCBI taxa by name
    b3repo.lineage(1280)                      # root ... Staphylococcus aureus
    b3repo.files(b3repo.find(q="GFP")[0])     # absolute paths of the package files

The repository location is ``$B3_REPOSITORY`` or /scratch/global/databases/biobank.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DEFAULT_ROOT = "/scratch/global/databases/biobank"
MAX_DEPTH = 64


def root(path=None) -> Path:
    return Path(path or os.environ.get("B3_REPOSITORY") or DEFAULT_ROOT)


def packages(repository=None, destination=None) -> list[dict]:
    """Published packages, newest first. One dict per package (the latest index line wins)."""
    index = root(repository) / "index" / "packages.jsonl"

    if not index.is_file():
        return []

    latest = {}

    with open(index, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()

            if line:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue

                latest[row.get("id")] = row

    rows = sorted(latest.values(), key=lambda r: r.get("published_at", ""), reverse=True)

    if destination:
        rows = [r for r in rows if r.get("destination", "internal") == destination]

    return rows


def find(q=None, taxid=None, repository=None, destination="internal") -> list[dict]:
    """Packages whose title contains ``q`` and whose lineage includes ``taxid``."""
    rows = packages(repository, destination)

    if q:
        rows = [r for r in rows if str(q).lower() in r.get("title", "").lower()]
    if taxid is not None:
        rows = [r for r in rows if str(taxid) in r.get("lineage_ids", [])]

    return rows


def package_dir(package, repository=None) -> Path:
    path = package["path"] if isinstance(package, dict) else package

    return root(repository) / path


def manifest(package, repository=None) -> dict:
    return json.loads((package_dir(package, repository) / "manifest.json").read_text(encoding="utf-8"))


def files(package, repository=None) -> list[Path]:
    """Absolute paths of the files listed in the package manifest."""
    base = package_dir(package, repository)

    return [base / f["path"] for f in manifest(package, repository)["files"]]


# --- taxonomy ------------------------------------------------------------------


def _taxonomy(repository=None):
    path = root(repository) / "index" / "taxonomy.sqlite"

    if not path.is_file():
        raise FileNotFoundError(f"Taxonomy index not found: {path}")

    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def taxon(taxid, repository=None) -> dict | None:
    db = _taxonomy(repository)

    try:
        row = db.execute("SELECT taxid, parent, rank, name FROM nodes WHERE taxid=?", (int(taxid),)).fetchone()
    finally:
        db.close()

    return {"taxid": row[0], "parent": row[1], "rank": row[2], "name": row[3]} if row else None


def lineage(taxid, repository=None) -> list[dict]:
    """From the root down to the taxon itself."""
    db = _taxonomy(repository)
    chain, seen, current = [], set(), int(taxid)

    try:
        while current not in seen and len(chain) < MAX_DEPTH:
            seen.add(current)

            row = db.execute("SELECT taxid, parent, rank, name FROM nodes WHERE taxid=?", (current,)).fetchone()

            if not row:
                break

            chain.append({"taxid": row[0], "rank": row[2], "name": row[3]})

            if row[1] == row[0]:
                break

            current = row[1]
    finally:
        db.close()

    return list(reversed(chain))


def search_taxa(prefix, limit=15, repository=None) -> list[dict]:
    """Scientific names starting with ``prefix``."""
    escaped = str(prefix).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    db = _taxonomy(repository)

    try:
        rows = db.execute(
            "SELECT taxid, rank, name FROM nodes WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE ORDER BY length(name), name LIMIT ?",
            (escaped + "%", int(limit)),
        ).fetchall()
    finally:
        db.close()

    return [{"taxid": r[0], "rank": r[1], "name": r[2]} for r in rows]
