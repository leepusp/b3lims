"""Reference data for bacterial species from the GTDB metadata already on DaVinci.

``build_index`` reads ``bac120_metadata_r*.tsv.gz`` once and keeps one summary row
per GTDB species (genome count, size, GC, CheckM2 quality, type material, the most
common isolation sources and countries) in a small SQLite file in the internal
repository. Without the index everything here returns empty.
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

TOP = 5
EMPTY = {"", "none", "na", "n/a", "not available", "missing", "unknown"}
SUFFIX = re.compile(r"_[A-Z]{1,2}$")


def gtdb_dir() -> Path:
    return Path(getattr(settings, "BIOBANK_GTDB_DIR", "/scratch/global/databases/gtdb/metadata"))


def index_path() -> Path:
    root = Path(getattr(settings, "BIOBANK_REPOSITORY_ROOT", "/scratch/global/databases/biobank"))

    return root / "index" / "gtdb.sqlite"


def latest_metadata(directory: Path | None = None) -> Path | None:
    """The bac120 metadata file of the newest release directory."""
    found = sorted((directory or gtdb_dir()).glob("*/bac120_metadata_r*.tsv*"))

    return found[-1] if found else None


def release_of(path: Path) -> str:
    match = re.search(r"_r(\d+)", path.name)

    return f"r{match.group(1)}" if match else path.parent.name


def _opener(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") if path.suffix == ".gz" else open(path, encoding="utf-8", errors="replace", newline="")


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _species(taxonomy: str) -> str:
    for part in taxonomy.split(";"):
        if part.startswith("s__"):
            return part[3:].strip()

    return ""


def build_index(metadata: Path | None = None, output: Path | None = None) -> dict:
    metadata = Path(metadata) if metadata else latest_metadata()

    if not metadata or not Path(metadata).is_file():
        raise FileNotFoundError(f"No bac120 metadata file found in {gtdb_dir()}")

    output = Path(output or index_path())
    output.parent.mkdir(parents=True, exist_ok=True)

    csv.field_size_limit(sys.maxsize)

    agg, taxids, rows_read = {}, {}, 0

    with _opener(Path(metadata)) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows_read += 1
            taxonomy = row.get("gtdb_taxonomy", "")
            name = _species(taxonomy)

            if not name:
                continue

            item = agg.setdefault(name, {
                "n": 0, "size": [], "gc": [], "complete": [], "contam": [], "type": 0, "lineage": taxonomy, "rep": "",
                "rep_size": None, "sources": Counter(), "countries": Counter(), "levels": Counter(),
            })

            item["n"] += 1

            for key, field in (("size", "genome_size"), ("gc", "gc_percentage"), ("complete", "checkm2_completeness"), ("contam", "checkm2_contamination")):
                value = _number(row.get(field))

                if value is not None:
                    item[key].append(value)

            if (row.get("gtdb_type_designation_ncbi_taxa") or "").strip().lower() not in EMPTY and "not type" not in (row.get("gtdb_type_designation_ncbi_taxa") or "").lower():
                item["type"] += 1

            if row.get("gtdb_representative") == "t":
                item["rep"] = row.get("accession", "")
                item["rep_size"] = _number(row.get("genome_size"))
                item["lineage"] = taxonomy

            for field, counter in (("ncbi_isolation_source", "sources"), ("ncbi_country", "countries"), ("ncbi_assembly_level", "levels")):
                text = (row.get(field) or "").strip()

                if text.lower() not in EMPTY:
                    item[counter][text.split(":")[0].strip() if counter == "countries" else text[:80]] += 1

            taxid = (row.get("ncbi_species_taxid") or "").strip()

            if taxid.isdigit():
                taxids.setdefault(taxid, Counter())[name] += 1

    tmp = output.with_name(output.name + f".{os.getpid()}.tmp")

    tmp.unlink(missing_ok=True)

    db = sqlite3.connect(tmp)

    try:
        db.execute("CREATE TABLE species (name TEXT PRIMARY KEY, base TEXT NOT NULL, data TEXT NOT NULL)")
        db.execute("CREATE TABLE taxid_map (taxid INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

        def mean(values):
            return round(sum(values) / len(values), 2) if values else None

        def median(values):
            values = sorted(values)

            return values[len(values) // 2] if values else None

        db.executemany("INSERT INTO species VALUES (?,?,?)", [
            (name, SUFFIX.sub("", name), json.dumps({
                "name": name, "genomes": i["n"], "lineage": i["lineage"], "representative": i["rep"],
                "genome_size_median": median(i["size"]), "genome_size_min": min(i["size"]) if i["size"] else None,
                "genome_size_max": max(i["size"]) if i["size"] else None, "gc_mean": mean(i["gc"]),
                "completeness_mean": mean(i["complete"]), "contamination_mean": mean(i["contam"]),
                "type_material_genomes": i["type"],
                "isolation_sources": i["sources"].most_common(TOP), "countries": i["countries"].most_common(TOP),
                "assembly_levels": i["levels"].most_common(TOP),
            }))
            for name, i in agg.items()
        ])
        db.executemany("INSERT INTO taxid_map VALUES (?,?)", [(int(t), c.most_common(1)[0][0]) for t, c in taxids.items()])
        db.execute("CREATE INDEX species_base ON species (base COLLATE NOCASE)")
        db.executemany("INSERT INTO meta VALUES (?,?)", [
            ("release", release_of(Path(metadata))), ("source", str(metadata)), ("genomes", str(rows_read)),
            ("built_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ])
        db.commit()
    except Exception:
        db.close()
        tmp.unlink(missing_ok=True)
        raise

    db.close()
    os.replace(tmp, output)

    return {"species": len(agg), "genomes": rows_read, "release": release_of(Path(metadata)), "path": str(output)}


def _connect():
    path = index_path()

    return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if path.is_file() else None


def available() -> bool:
    return index_path().is_file()


def release() -> str:
    db = _connect()

    if not db:
        return ""

    try:
        row = db.execute("SELECT value FROM meta WHERE key='release'").fetchone()

        return row[0] if row else ""
    finally:
        db.close()


def for_species(name="", taxid=None) -> dict | None:
    """Summary of the GTDB species matching an NCBI species taxid or a species name (GTDB suffixes like ``_C`` ignored)."""
    db = _connect()

    if not db:
        return None

    try:
        row = None

        if str(taxid or "").isdigit():
            hit = db.execute("SELECT name FROM taxid_map WHERE taxid=?", (int(taxid),)).fetchone()

            if hit:
                row = db.execute("SELECT data FROM species WHERE name=?", (hit[0],)).fetchone()

        if row is None and (name or "").strip():
            row = db.execute("SELECT data FROM species WHERE base=? COLLATE NOCASE ORDER BY length(name) LIMIT 1", (name.strip(),)).fetchone()
    finally:
        db.close()

    if not row:
        return None

    data = json.loads(row[0])

    data["release"] = release()

    return data


def _lineage(taxonomy: str):
    """The GTDB lineage string as a list of {taxid, rank, name} like the NCBI one (no taxids in GTDB)."""
    ranks = {"d": "domain", "p": "phylum", "c": "class", "o": "order", "f": "family", "g": "genus", "s": "species"}

    return [{"taxid": "", "rank": ranks.get(part[:1], "no rank"), "name": part[3:]} for part in taxonomy.split(";") if len(part) > 3]


def lineage_of(data: dict):
    return _lineage(data.get("lineage", ""))


def get(name: str) -> dict | None:
    """One GTDB species by its exact name (with any ``_C`` suffix)."""
    db = _connect()

    if not db or not (name or "").strip():
        return None

    try:
        row = db.execute("SELECT data FROM species WHERE name=? COLLATE NOCASE", (name.strip(),)).fetchone()
    finally:
        db.close()

    if not row:
        return None

    data = json.loads(row[0])

    data["release"] = release()

    return data


def search(query: str, limit: int = 12) -> list[dict]:
    """GTDB species whose name starts with the query (``E. coli`` and ``ecoli`` work too), largest first."""
    query = " ".join((query or "").split())
    db = _connect()

    if not db or not query:
        return []

    def esc(text):
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    patterns = [esc(query) + "%"]
    short = re.match(r"^([A-Za-z])\.?\s*([a-z][a-z\-]+)$", query)

    if short:
        patterns.append(f"{short.group(1)}% {short.group(2)}%")

    found, seen = [], set()

    try:
        for pattern in patterns:
            for name, data in db.execute(
                "SELECT name, data FROM species WHERE base LIKE ? ESCAPE '\\' COLLATE NOCASE", (pattern,)
            ).fetchall():
                if name in seen:
                    continue

                seen.add(name)
                info = json.loads(data)
                found.append({"name": name, "genomes": info["genomes"], "lineage": info["lineage"]})
    finally:
        db.close()

    found.sort(key=lambda r: (-r["genomes"], len(r["name"])))

    return found[:limit]
