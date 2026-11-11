"""Organisms of a sample: picked from the local NCBI taxonomy index or typed by hand."""

from __future__ import annotations

import json
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models.samples.organisms import SampleOrganism
from core.services import gtdb_local, taxonomy_local

MAX_ORGANISMS = 25
BACTERIA, ARCHAEA, VIRUSES = 2, 2157, 10239

# Main organisms and members must belong to these branches of the taxonomy for each sample type.
# Hosts and associated organisms are never restricted. None means any organism.
SCOPES = {
    "Bacterium (Host)": (BACTERIA, ARCHAEA),
    "Phage (Virus)": (VIRUSES,),
}
SCOPE_LABELS = {
    "Bacterium (Host)": "Bacteria and Archaea",
    "Phage (Virus)": "Viruses",
}
ROLES = {value for value, _ in SampleOrganism.ROLE_CHOICES}
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def scope_for(sample_type):
    return SCOPES.get(sample_type or "")


def scope_label(sample_type):
    return SCOPE_LABELS.get(sample_type or "", "Any organism")


def in_scope(lineage, scope):
    return scope is None or any(node["taxid"] in scope for node in lineage)


def _brief(lineage):
    """A short path for the result list: the last two named ranks before the taxon."""
    names = [n["name"] for n in lineage[:-1] if n["rank"] in ("phylum", "class", "order", "family", "genus")]

    return " > ".join(names[-2:])


def search(query, sample_type="", limit=12, source="ncbi"):
    """Taxa of the local databases whose name matches ``query``, limited to the sample type's branch.

    ``source`` is ``ncbi``, ``gtdb`` or ``all`` (NCBI first, then GTDB for bacteria)."""
    if source == "all":
        first = search(query, sample_type, limit, "ncbi")

        if scope_for(sample_type) is None or BACTERIA not in (scope_for(sample_type) or ()):
            return first

        second = search(query, sample_type, 4, SourceGTDB)

        return {
            "available": first["available"] or second["available"], "results": first["results"][:8] + second["results"],
            "scope": "NCBI Taxonomy and GTDB", "source": "all",
        }

    if source == SourceGTDB:
        if not gtdb_local.available():
            return {"available": False, "results": [], "scope": "Bacteria (GTDB)", "source": source}

        results = []

        for hit in gtdb_local.search(query, limit):
            chain = gtdb_local.lineage_of(hit)
            results.append({
                "taxid": "", "gtdb": hit["name"], "rank": "species", "name": _gtdb_base(hit["name"]),
                "path": _brief(chain), "genus": next((c["name"] for c in chain if c["rank"] == "genus"), ""),
                "ranks": {c["rank"]: c["name"] for c in chain}, "genomes": hit["genomes"], "source": "gtdb",
            })

        return {"available": True, "results": results, "scope": "Bacteria (GTDB)", "source": source}

    if not taxonomy_local.available():
        return {"available": False, "results": [], "scope": scope_label(sample_type), "source": "ncbi"}

    scope = scope_for(sample_type)
    results = []

    for hit in taxonomy_local.search(query, limit=60):
        chain = taxonomy_local.lineage(hit["taxid"])

        if not in_scope(chain, scope):
            continue

        genus = next((c["name"] for c in chain if c.get("rank") == "genus"), "")
        ranks = {c["rank"]: c["name"] for c in chain if c.get("rank") and c["rank"] != "no rank"}
        results.append({**hit, "path": _brief(chain), "genus": genus, "ranks": ranks, "source": "ncbi"})

        if len(results) >= limit:
            break

    results.sort(key=lambda r: (r["rank"] not in ("species", "strain", "no rank", "subspecies"), "matched" in r, len(r["name"])))

    return {"available": True, "results": results, "scope": scope_label(sample_type), "source": "ncbi"}


SourceGTDB = "gtdb"


def _gtdb_base(name):
    return re.sub(r"_[A-Z]{1,2}$", "", name)


def _text(value, limit, label):
    value = str(value or "").strip()

    if CONTROL.search(value):
        raise ValidationError(f"{label} contains invalid characters.")
    if len(value) > limit:
        raise ValidationError(f"{label} is too long (at most {limit} characters).")

    return value


def parse(raw):
    """The rows posted by the form (a JSON list); an empty or missing value means no rows."""
    if raw in (None, "", "[]"):
        return []

    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise ValidationError("The organism list is not valid.")

    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValidationError("The organism list is not valid.")

    return rows


def clean(rows, sample_type=""):
    """Validated rows ready to store. The taxonomy index, not the browser, supplies names and lineages."""
    rows = [r for r in rows if any(str(r.get(key) or "").strip() for key in ("name", "taxid", "gtdb"))]

    if len(rows) > MAX_ORGANISMS:
        raise ValidationError(f"A sample can list at most {MAX_ORGANISMS} organisms.")

    scope = scope_for(sample_type)
    out, seen = [], set()

    for number, row in enumerate(rows, 1):
        label = f"Organism {number}"
        strain = _text(row.get("strain"), 100, f"{label} strain")
        notes = _text(row.get("notes"), 255, f"{label} notes")
        role = str(row.get("role") or SampleOrganism.ROLE_MEMBER)

        if role not in ROLES:
            raise ValidationError(f"{label} has an invalid role.")

        taxid = str(row.get("taxid") or "").strip()

        if str(row.get("source") or "") == SourceGTDB and not taxid:
            data = gtdb_local.get(str(row.get("gtdb") or row.get("name") or ""))

            if data is None:
                raise ValidationError(f"{label}: this species is not in the local GTDB copy.")

            chain = gtdb_local.lineage_of(data)

            if role in (SampleOrganism.ROLE_PRIMARY, SampleOrganism.ROLE_MEMBER) and not in_scope([{"taxid": BACTERIA, "name": "Bacteria"}], scope):
                raise ValidationError(f"{label} ({_gtdb_base(data['name'])}) is a bacterium, which this sample type does not take.")

            item = {
                "name": _gtdb_base(data["name"]), "taxon_id": data["name"], "rank": "species", "lineage": chain,
                "source": SampleOrganism.SOURCE_GTDB, "taxonomy_version": data.get("release", ""),
            }
        elif taxid:
            if not taxid.isdigit():
                raise ValidationError(f"{label} has an invalid taxonomy id.")

            node = taxonomy_local.get(taxid)

            if node is None:
                raise ValidationError(f"{label}: taxonomy id {taxid} is not in the local taxonomy database.")

            chain = taxonomy_local.lineage(taxid)

            if role in (SampleOrganism.ROLE_PRIMARY, SampleOrganism.ROLE_MEMBER) and not in_scope(chain, scope):
                raise ValidationError(f"{label} ({node['name']}) is not in {scope_label(sample_type)}, which this sample type needs.")

            item = {
                "name": node["name"], "taxon_id": str(node["taxid"]), "rank": node["rank"], "lineage": chain,
                "source": SampleOrganism.SOURCE_NCBI, "taxonomy_version": taxonomy_local.version(),
            }
        else:
            name = _text(row.get("name"), 255, f"{label} name")

            if not name:
                raise ValidationError(f"{label} needs a name.")

            item = {
                "name": name, "taxon_id": "", "rank": "", "lineage": [], "source": SampleOrganism.SOURCE_MANUAL,
                "taxonomy_version": "",
            }

        key = (item["taxon_id"] or item["name"].lower(), strain.lower())

        if key in seen:
            raise ValidationError(f"{label} ({item['name']}) is listed twice.")

        seen.add(key)
        out.append({**item, "strain": strain, "notes": notes, "role": role})

    # Exactly one main organism, listed first.
    if out:
        first_main = next((i for i, r in enumerate(out) if r["role"] == SampleOrganism.ROLE_PRIMARY), 0)

        for i, row in enumerate(out):
            if i == first_main:
                row["role"] = SampleOrganism.ROLE_PRIMARY
            elif row["role"] == SampleOrganism.ROLE_PRIMARY:
                row["role"] = SampleOrganism.ROLE_MEMBER

        out.insert(0, out.pop(first_main))

    return out


def summary(rows):
    """The text kept in ``Sample.organism_name``: the main organism and the members, hosts left out."""
    names = [
        f"{r['name']} {r.get('strain') or ''}".strip()
        for r in rows
        if r["role"] in (SampleOrganism.ROLE_PRIMARY, SampleOrganism.ROLE_MEMBER)
    ]

    if len(names) <= 3:
        return " + ".join(names)[:255]

    return (" + ".join(names[:3]) + f" + {len(names) - 3} more")[:255]


@transaction.atomic
def replace(sample, rows):
    sample.organisms.all().delete()
    SampleOrganism.objects.bulk_create(
        [
            SampleOrganism(
                sample=sample, position=i, role=r["role"], name=r["name"], strain=r["strain"], source=r["source"],
                taxon_id=r["taxon_id"], rank=r["rank"], lineage=r["lineage"], taxonomy_version=r["taxonomy_version"],
                notes=r["notes"],
            )
            for i, r in enumerate(rows)
        ]
    )


def serialize(sample):
    return [
        {
            "name": o.name, "strain": o.strain, "role": o.role, "rank": o.rank,
            "taxid": "" if o.source == SampleOrganism.SOURCE_GTDB else o.taxon_id,
            "gtdb": o.taxon_id if o.source == SampleOrganism.SOURCE_GTDB else "",
            "source": o.source, "notes": o.notes, "path": _brief(o.lineage) if o.lineage else "",
        }
        for o in sample.organisms.all()
    ]


def form_rows(rows):
    """Cleaned rows in the shape the form script reads (see ``serialize``)."""
    return [
        {
            "name": r["name"], "strain": r["strain"], "role": r["role"], "rank": r["rank"],
            "taxid": "" if r["source"] == SampleOrganism.SOURCE_GTDB else r["taxon_id"],
            "gtdb": r["taxon_id"] if r["source"] == SampleOrganism.SOURCE_GTDB else "",
            "source": r["source"], "notes": r["notes"], "path": _brief(r["lineage"]) if r["lineage"] else "",
        }
        for r in rows
    ]


def main_taxid(sample):
    """The taxonomy id of the main organism, or "" when it was typed by hand or the sample has none."""
    main = sample.organisms.filter(role=SampleOrganism.ROLE_PRIMARY, source=SampleOrganism.SOURCE_NCBI).first()

    return main.taxon_id if main else ""


# What the NCBI lineage of a virus lets us infer. Always shown as "inferred", never as measured.
GENOME_TYPES = (
    ("Leviviricetes", "ssRNA"), ("Cystoviridae", "dsRNA"), ("Monodnaviria", "ssDNA"), ("Microviridae", "ssDNA"),
    ("Inoviridae", "ssDNA"), ("Duplodnaviria", "dsDNA"), ("Varidnaviria", "dsDNA"), ("Adnaviria", "dsDNA"),
    ("Caudoviricetes", "dsDNA"), ("Caudovirales", "dsDNA"),
)
MORPHOTYPES = (("Myoviridae", "myovirus"), ("Siphoviridae", "siphovirus"), ("Podoviridae", "podovirus"))


def infer_virus(chain):
    names = {c["name"] for c in chain}
    out = {}

    for name, value in GENOME_TYPES:
        if name in names:
            out["genome_type"] = {"value": value, "basis": name}

            break

    for name, value in MORPHOTYPES:
        if name in names:
            out["morphotype"] = {"value": value, "basis": name}

            break

    return out


def species_of(chain):
    return next((c for c in reversed(chain) if c.get("rank") == "species"), None)


def details(taxid, sample_type=""):
    """Everything the form can show about one picked taxon: NCBI names, GTDB reference data, inferred virus traits."""
    info = taxonomy_local.details(taxid)

    if info is None:
        return None

    chain = taxonomy_local.lineage(info["taxid"])
    species = species_of(chain)
    ranks = {c["rank"]: c["name"] for c in chain if c.get("rank") and c["rank"] != "no rank"}
    warnings = []
    out = {**info, "lineage": chain, "ranks": ranks, "gtdb": None, "inferred": {}, "warnings": warnings}

    if in_scope(chain, (VIRUSES,)):
        out["inferred"] = infer_virus(chain)

        if not ranks.get("genus") and not ranks.get("family"):
            warnings.append("NCBI has no genus or family for this virus (unclassified), so only the name can be used.")
    elif in_scope(chain, (BACTERIA, ARCHAEA)):
        if gtdb_local.available() and species:
            out["gtdb"] = gtdb_local.for_species(species["name"], species["taxid"])
    if info["rank"] == "species" and re.search(r"\bsp\.", info["name"]):
        warnings.append("This is an unspecified species (sp.): the species field is left empty.")

    return out


def with_catalog(found):
    """``found`` plus the list of items the user can attach to the sample."""
    from core.services import reference_data

    return None if found is None else {**found, "catalog": reference_data.catalog(found)}


def details_gtdb(name):
    """The card of a GTDB species picked in the form, with the NCBI entry of the same name when there is one."""
    data = gtdb_local.get(name)

    if data is None:
        return None

    base = _gtdb_base(data["name"])
    chain = gtdb_local.lineage_of(data)
    found = None

    for hit in taxonomy_local.search(base, limit=10):
        if hit["name"].lower() == base.lower() and hit["rank"] == "species" and "matched" not in hit:
            found = details(hit["taxid"], "Bacterium (Host)")

            break

    out = found or {
        "taxid": "", "rank": "species", "name": base, "synonyms": [], "common_names": [], "authority": [], "division": "",
        "genetic_code": "", "lineage": chain, "ranks": {}, "inferred": {}, "warnings": [],
    }

    return {**out, "ranks": {c["rank"]: c["name"] for c in chain}, "gtdb": data, "source": "gtdb", "name": base}
