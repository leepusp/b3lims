"""ICTV virus taxonomy from the Virus Metadata Resource (VMR) spreadsheet kept on the server.

``build_index`` reads ``VMR_MSL*.xlsx`` once and keeps one row per ICTV species (taxonomy from realm to
species, the exemplar virus with its GenBank accession, genome composition and host source) in a small
SQLite file in the internal repository. Without the index everything here returns empty.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

RANKS = ["realm", "subrealm", "kingdom", "subkingdom", "phylum", "subphylum", "class", "subclass", "order", "suborder", "family", "subfamily", "genus", "subgenus", "species"]
PHAGE_HOSTS = ("bacteria", "archaea")
GENOME_TYPES = ("dsDNA", "ssDNA", "dsRNA", "ssRNA")
FORMULA = re.compile(r'"([^"]*)"\)\s*$')


def ictv_dir() -> Path:
    return Path(getattr(settings, "BIOBANK_ICTV_DIR", "/scratch/global/databases/ictv"))


def index_path() -> Path:
    root = Path(getattr(settings, "BIOBANK_REPOSITORY_ROOT", "/scratch/global/databases/biobank"))

    return root / "index" / "ictv.sqlite"


def latest_vmr(directory: Path | None = None) -> Path | None:
    found = sorted(p for p in (directory or ictv_dir()).glob("*/VMR*.xlsx") if not p.name.startswith("~"))

    return found[-1] if found else None


def _plain(value) -> str:
    """Cell text; ``=HYPERLINK("url","text")`` formulas give their visible text."""
    text = "" if value is None else str(value).strip()
    match = FORMULA.search(text) if text.startswith("=HYPERLINK") else None

    return match.group(1).strip() if match else text


def genome_type_of(composition: str) -> str:
    """The form's genome type for an ICTV composition such as ``dsDNA`` or ``ssRNA(+)``; empty for the rest."""
    text = (composition or "").strip()

    if "RT" in text:
        return ""

    return next((t for t in GENOME_TYPES if text.startswith(t)), "")


def is_phage(hosts) -> bool:
    return any(any(h in (host or "").lower() for h in PHAGE_HOSTS) for host in hosts)


def build_index(vmr: Path | None = None, output: Path | None = None) -> dict:
    import openpyxl

    vmr = Path(vmr) if vmr else latest_vmr()

    if not vmr or not Path(vmr).is_file():
        raise FileNotFoundError(f"No VMR spreadsheet found in {ictv_dir()}")

    workbook = openpyxl.load_workbook(vmr, read_only=True, data_only=False)
    sheet = next((ws for ws in workbook.worksheets if ws.title.upper().startswith("VMR")), None)

    if sheet is None:
        raise ValueError("The spreadsheet has no sheet named VMR ...")

    rows = sheet.iter_rows(values_only=True)
    header = [(_plain(c)).lower() for c in next(rows)]

    def col(name):
        return header.index(name) if name in header else None

    index = {name: col(name) for name in (RANKS + ["exemplar or additional isolate", "virus name(s)", "virus name abbreviation(s)",
                                                  "virus isolate designation", "virus genbank accession", "genome coverage", "genome", "host source", "ictv_id"])}

    if index["species"] is None:
        raise ValueError("The VMR has no Species column.")

    species = {}

    def cell(row, name):
        i = index.get(name)

        return _plain(row[i]) if i is not None and i < len(row) else ""

    for row in rows:
        name = cell(row, "species")

        if not name:
            continue

        item = species.setdefault(name, {"name": name, "lineage": [], "ictv_id": cell(row, "ictv_id"), "exemplars": [], "hosts": [], "composition": []})

        if not item["lineage"]:
            item["lineage"] = [{"taxid": "", "rank": rank, "name": cell(row, rank)} for rank in RANKS if cell(row, rank)]

        host, composition = cell(row, "host source"), cell(row, "genome")

        if host and host not in item["hosts"]:
            item["hosts"].append(host)

        if composition and composition not in item["composition"]:
            item["composition"].append(composition)

        if cell(row, "exemplar or additional isolate") == "E":
            item["exemplars"].append({
                "name": cell(row, "virus name(s)"), "abbreviation": cell(row, "virus name abbreviation(s)"), "isolate": cell(row, "virus isolate designation"),
                "accession": cell(row, "virus genbank accession"), "coverage": cell(row, "genome coverage"), "genome": composition, "host": host,
            })

    output = Path(output or index_path())
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + f".{os.getpid()}.tmp")

    tmp.unlink(missing_ok=True)

    db = sqlite3.connect(tmp)

    try:
        db.execute("CREATE TABLE species (name TEXT PRIMARY KEY, phage INTEGER NOT NULL, data TEXT NOT NULL)")
        db.execute("CREATE TABLE terms (term TEXT NOT NULL COLLATE NOCASE, species TEXT NOT NULL)")
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

        terms = []

        for name, item in species.items():
            db.execute("INSERT INTO species VALUES (?,?,?)", (name, int(is_phage(item["hosts"])), json.dumps(item)))
            names = {name}
            names.update(c["name"] for c in item["lineage"] if c["rank"] in ("genus", "family", "subfamily"))

            for e in item["exemplars"]:
                names.update(x for x in (e["name"], e["abbreviation"]) if x)

            terms.extend((term, name) for term in names)

        db.executemany("INSERT INTO terms VALUES (?,?)", terms)
        db.execute("CREATE INDEX terms_term ON terms (term COLLATE NOCASE)")
        db.executemany("INSERT INTO meta VALUES (?,?)", [
            ("release", re.sub(r"\.xlsx$", "", vmr.name)), ("source", str(vmr)), ("built_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ])
        db.commit()
    except Exception:
        db.close()
        tmp.unlink(missing_ok=True)
        raise

    db.close()
    os.replace(tmp, output)

    return {"species": len(species), "phages": sum(is_phage(i["hosts"]) for i in species.values()), "release": vmr.name, "path": str(output)}


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


def get(name: str) -> dict | None:
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


def search(query: str, limit: int = 12, phages_only: bool = True) -> list[dict]:
    """ICTV species whose name, genus, family or exemplar virus name starts with the query, species names first."""
    query = " ".join((query or "").split())
    db = _connect()

    if not db or len(query) < 2:
        return []

    like = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    found, seen = [], set()

    try:
        for term, name, data in db.execute(
            "SELECT t.term, s.name, s.data FROM terms t JOIN species s ON s.name = t.species "
            "WHERE t.term LIKE ? ESCAPE '\\' COLLATE NOCASE" + (" AND s.phage = 1" if phages_only else "") + " ORDER BY length(t.term) LIMIT 400",
            (like + "%",),
        ).fetchall():
            if name in seen:
                continue

            seen.add(name)
            item = json.loads(data)
            found.append({"name": name, "matched": "" if term.lower() == name.lower() else term, "lineage": item["lineage"], "hosts": item["hosts"], "genomes": item["composition"]})
    finally:
        db.close()

    found.sort(key=lambda r: (bool(r["matched"]), len(r["name"])))

    return found[:limit]
