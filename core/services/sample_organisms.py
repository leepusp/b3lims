"""Organisms of a sample: picked from the local NCBI taxonomy index or typed by hand."""

from __future__ import annotations

import json
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models.samples.organisms import SampleOrganism
from core.services import taxonomy_local

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


def search(query, sample_type="", limit=12):
    """Taxa of the local index whose name starts with ``query``, limited to the sample type's branch."""
    if not taxonomy_local.available():
        return {"available": False, "results": [], "scope": scope_label(sample_type)}

    scope = scope_for(sample_type)
    results = []

    for hit in taxonomy_local.search(query, limit=60):
        chain = taxonomy_local.lineage(hit["taxid"])

        if not in_scope(chain, scope):
            continue

        genus = next((c["name"] for c in chain if c.get("rank") == "genus"), "")
        results.append({**hit, "path": _brief(chain), "genus": genus})

        if len(results) >= limit:
            break

    results.sort(key=lambda r: (r["rank"] not in ("species", "strain", "no rank", "subspecies"), len(r["name"])))

    return {"available": True, "results": results, "scope": scope_label(sample_type)}


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
    rows = [r for r in rows if str(r.get("name") or "").strip() or str(r.get("taxid") or "").strip()]

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

        if taxid:
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
            "name": o.name, "strain": o.strain, "role": o.role, "taxid": o.taxon_id, "rank": o.rank,
            "source": o.source, "notes": o.notes, "path": _brief(o.lineage) if o.lineage else "",
        }
        for o in sample.organisms.all()
    ]


def form_rows(rows):
    """Cleaned rows in the shape the form script reads (see ``serialize``)."""
    return [
        {
            "name": r["name"], "strain": r["strain"], "role": r["role"], "taxid": r["taxon_id"], "rank": r["rank"],
            "source": r["source"], "notes": r["notes"], "path": _brief(r["lineage"]) if r["lineage"] else "",
        }
        for r in rows
    ]


def main_taxid(sample):
    """The taxonomy id of the main organism, or "" when it was typed by hand or the sample has none."""
    main = sample.organisms.filter(role=SampleOrganism.ROLE_PRIMARY).first()

    return main.taxon_id if main else ""
