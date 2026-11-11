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
EXTRA_KINDS = {"synonym", "genbank synonym", "equivalent name", "common name", "genbank common name", "authority", "includes", "acronym", "genbank acronym"}


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


def _int(cols, position):
    try:
        return int(cols[position])
    except (IndexError, ValueError):
        return None


def _load_small(db, path, table, minimum, make):
    """Fill a small lookup table from an optional dump file."""
    if not path.is_file():
        return

    rows = []

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            cols = _fields(line)

            if len(cols) >= minimum:
                try:
                    rows.append(make(cols))
                except ValueError:
                    continue

    marks = ",".join("?" * len(rows[0])) if rows else "?"

    if rows:
        db.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({marks})", rows)


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
        db.execute(
            "CREATE TABLE nodes (taxid INTEGER PRIMARY KEY, parent INTEGER NOT NULL, rank TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', "
            "division INTEGER, gencode INTEGER)"
        )
        db.execute("CREATE TABLE extra_names (taxid INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL)")
        db.execute("CREATE TABLE divisions (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        db.execute("CREATE TABLE gencodes (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        db.execute("CREATE TABLE merged (old INTEGER PRIMARY KEY, new INTEGER NOT NULL)")
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

        batch, total, extras = [], 0, []

        with open(nodes_file, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                cols = _fields(line)

                batch.append((int(cols[0]), int(cols[1]), cols[2], "", _int(cols, 4), _int(cols, 6)))

                if len(batch) >= BATCH:
                    db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?)", batch)
                    total += len(batch)
                    batch = []

        if batch:
            db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?)", batch)
            total += len(batch)

        batch = []

        with open(names_file, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                cols = _fields(line)

                if len(cols) < 4:
                    continue

                if cols[3] == "scientific name":
                    batch.append((cols[1], int(cols[0])))
                elif cols[3] in EXTRA_KINDS:
                    extras.append((int(cols[0]), cols[1], cols[3]))

                if len(batch) >= BATCH:
                    db.executemany("UPDATE nodes SET name=? WHERE taxid=?", batch)
                    batch = []

                if len(extras) >= BATCH:
                    db.executemany("INSERT INTO extra_names VALUES (?,?,?)", extras)
                    extras = []

        if batch:
            db.executemany("UPDATE nodes SET name=? WHERE taxid=?", batch)

        if extras:
            db.executemany("INSERT INTO extra_names VALUES (?,?,?)", extras)

        _load_small(db, directory / "division.dmp", "divisions", 3, lambda c: (int(c[0]), c[2]))
        _load_small(db, directory / "gencode.dmp", "gencodes", 4, lambda c: (int(c[0]), c[2]))
        _load_small(db, directory / "merged.dmp", "merged", 2, lambda c: (int(c[0]), int(c[1])))
        db.execute("CREATE INDEX extra_names_taxid ON extra_names (taxid)")

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
        number = int(taxid)
        row = db.execute("SELECT taxid, parent, rank, name FROM nodes WHERE taxid=?", (number,)).fetchone()

        if row is None:
            # a taxon NCBI merged into another one
            try:
                moved = db.execute("SELECT new FROM merged WHERE old=?", (number,)).fetchone()
            except sqlite3.OperationalError:
                moved = None

            if moved:
                row = db.execute("SELECT taxid, parent, rank, name FROM nodes WHERE taxid=?", (moved[0],)).fetchone()
    except (TypeError, ValueError):
        return None
    finally:
        db.close()

    return {"taxid": row[0], "parent": row[1], "rank": row[2], "name": row[3]} if row else None


def details(taxid) -> dict | None:
    """Names, division and genetic code of one taxon. Fields an older index lacks are left out."""
    node = get(taxid)

    if node is None:
        return None

    db = _connect()
    out = {"taxid": node["taxid"], "rank": node["rank"], "name": node["name"], "synonyms": [], "common_names": [], "authority": [], "division": "", "genetic_code": ""}

    try:
        for name, kind in db.execute("SELECT name, kind FROM extra_names WHERE taxid=? ORDER BY name", (node["taxid"],)).fetchall():
            if kind == "authority":
                out["authority"].append(name)
            elif "common" in kind:
                out["common_names"].append(name)
            elif kind in ("synonym", "genbank synonym", "equivalent name", "includes"):
                out["synonyms"].append(name)

        row = db.execute(
            "SELECT d.name, g.name FROM nodes n LEFT JOIN divisions d ON d.id = n.division LEFT JOIN gencodes g ON g.id = n.gencode WHERE n.taxid=?",
            (node["taxid"],),
        ).fetchone()

        if row:
            out["division"], out["genetic_code"] = row[0] or "", row[1] or ""
    except sqlite3.OperationalError:
        pass
    finally:
        db.close()

    return out


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
