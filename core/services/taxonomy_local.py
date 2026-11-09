"""Local NCBI taxonomy, read from the taxdump already on DaVinci.

``build_index`` turns ``nodes.dmp`` and ``names.dmp`` into a small SQLite file
inside the internal repository, so lookups take milliseconds and Jupyter or
Galaxy tools can open the same file. Without the index everything here returns
empty and callers fall back to a typed taxon.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

MAX_DEPTH = 64
BATCH = 50000
SEP = "\t|"


def taxdump_dir() -> Path:
    return Path(getattr(settings, "BIOBANK_TAXONOMY_DIR", "/scratch/global/databases/taxonomy"))


def index_path() -> Path:
    root = Path(getattr(settings, "BIOBANK_REPOSITORY_ROOT", "/scratch/global/databases/biobank"))

    return root / "index" / "taxonomy.sqlite"


def taxdump_version(directory: Path | None = None) -> str:
    """Date of the dump (modification time of names.dmp), e.g. ``2026-06-05``."""
    names = (directory or taxdump_dir()) / "names.dmp"

    try:
        return datetime.fromtimestamp(names.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except OSError:
        return ""


def _fields(line: str) -> list[str]:
    return [part.strip() for part in line.rstrip("\n").rstrip("|").split("\t|\t")]


def build_index(directory: Path | None = None, output: Path | None = None) -> dict:
    """Build the SQLite index from a taxdump directory. Returns a small summary."""
    directory = Path(directory or taxdump_dir())
    output = Path(output or index_path())
    nodes_file, names_file = directory / "nodes.dmp", directory / "names.dmp"

    if not nodes_file.is_file() or not names_file.is_file():
        raise FileNotFoundError(f"nodes.dmp and names.dmp are required in {directory}")

    output.parent.mkdir(parents=True, exist_ok=True)

    tmp = output.with_name(output.name + f".{os.getpid()}.tmp")

    tmp.unlink(missing_ok=True)

    db = sqlite3.connect(tmp)

    try:
        db.execute("CREATE TABLE nodes (taxid INTEGER PRIMARY KEY, parent INTEGER NOT NULL, rank TEXT NOT NULL, name TEXT NOT NULL DEFAULT '')")
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

        batch, total = [], 0

        with open(nodes_file, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                cols = _fields(line)

                batch.append((int(cols[0]), int(cols[1]), cols[2], ""))

                if len(batch) >= BATCH:
                    db.executemany("INSERT INTO nodes VALUES (?,?,?,?)", batch)
                    total += len(batch)
                    batch = []

        if batch:
            db.executemany("INSERT INTO nodes VALUES (?,?,?,?)", batch)
            total += len(batch)

        batch = []

        with open(names_file, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                cols = _fields(line)

                if len(cols) >= 4 and cols[3] == "scientific name":
                    batch.append((cols[1], int(cols[0])))

                if len(batch) >= BATCH:
                    db.executemany("UPDATE nodes SET name=? WHERE taxid=?", batch)
                    batch = []

        if batch:
            db.executemany("UPDATE nodes SET name=? WHERE taxid=?", batch)

        db.execute("CREATE INDEX nodes_name ON nodes (name COLLATE NOCASE)")
        db.executemany("INSERT INTO meta VALUES (?,?)", [
            ("version", taxdump_version(directory)),
            ("source", str(directory)),
            ("built_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            ("nodes", str(total)),
        ])
        db.commit()
    except Exception:
        db.close()
        tmp.unlink(missing_ok=True)
        raise

    db.close()
    os.replace(tmp, output)

    return {"nodes": total, "version": taxdump_version(directory), "path": str(output)}


def _connect():
    path = index_path()

    if not path.is_file():
        return None

    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def available() -> bool:
    return index_path().is_file()


def version() -> str:
    db = _connect()

    if not db:
        return ""

    try:
        row = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()

        return row[0] if row else ""
    finally:
        db.close()


def get(taxid) -> dict | None:
    db = _connect()

    if not db:
        return None

    try:
        row = db.execute("SELECT taxid, parent, rank, name FROM nodes WHERE taxid=?", (int(taxid),)).fetchone()
    except (TypeError, ValueError):
        return None
    finally:
        db.close()

    return {"taxid": row[0], "parent": row[1], "rank": row[2], "name": row[3]} if row else None


def lineage(taxid) -> list[dict]:
    """From the root down to the taxon itself."""
    db = _connect()

    if not db:
        return []

    chain, seen = [], set()

    try:
        current = int(taxid)

        while current not in seen and len(chain) < MAX_DEPTH:
            seen.add(current)

            row = db.execute("SELECT taxid, parent, rank, name FROM nodes WHERE taxid=?", (current,)).fetchone()

            if not row:
                break

            chain.append({"taxid": row[0], "rank": row[2], "name": row[3]})

            if row[1] == row[0]:
                break

            current = row[1]
    except (TypeError, ValueError):
        return []
    finally:
        db.close()

    return list(reversed(chain))


def search(query: str, limit: int = 15) -> list[dict]:
    """Scientific names starting with ``query`` (or the taxid when it is a number)."""
    query = (query or "").strip()
    db = _connect()

    if not db or not query:
        return []

    try:
        if query.isdigit():
            rows = db.execute("SELECT taxid, rank, name FROM nodes WHERE taxid=?", (int(query),)).fetchall()
        else:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = db.execute(
                "SELECT taxid, rank, name FROM nodes WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE ORDER BY length(name), name LIMIT ?",
                (escaped + "%", int(limit)),
            ).fetchall()
    finally:
        db.close()

    return [{"taxid": r[0], "rank": r[1], "name": r[2]} for r in rows]
