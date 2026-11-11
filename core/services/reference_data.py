"""Reference metadata a user can attach to a sample, taken from the local taxonomy and GTDB copies.

``catalog`` lists what is available for a taxon (every item has a source, a key and a readable value);
the form lets the user tick the ones to keep and ``attach`` stores only those, recomputing the values
on the server so the browser cannot invent them.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models.samples.organisms import SampleOrganism
from core.models.samples.reference_data import SampleReferenceData
from core.services import gtdb_local, sample_organisms, taxonomy_local

MAX_ITEMS = 120
NCBI, GTDB, INFERRED = "ncbi", "gtdb", "inferred"
SOURCE_LABELS = {NCBI: "NCBI Taxonomy", GTDB: "GTDB", INFERRED: "Inferred from the lineage"}


def _number(value, digits=0):
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return ""


def _pairs(pairs):
    return "; ".join(f"{name} ({count})" for name, count in pairs or [])


def catalog(details):
    """Items available for one taxon, from the dict returned by ``sample_organisms.details`` or ``details_gtdb``."""
    items = []
    ncbi_version = taxonomy_local.version()

    def add(source, version, group, key, label, value):
        value = str(value or "").strip()

        if value:
            items.append({"source": source, "version": version, "group": group, "key": key, "label": label, "value": value})

    if details.get("taxid"):
        lineage = " > ".join(c["name"] for c in details["lineage"] if c["rank"] not in ("no rank", "clade"))

        add(NCBI, ncbi_version, "Taxonomy", "taxid", "NCBI taxonomy id", details["taxid"])
        add(NCBI, ncbi_version, "Taxonomy", "rank", "Rank", details["rank"])
        add(NCBI, ncbi_version, "Taxonomy", "lineage", "NCBI lineage", lineage)
        add(NCBI, ncbi_version, "Taxonomy", "synonyms", "Synonyms", "; ".join(details["synonyms"][:10]))
        add(NCBI, ncbi_version, "Taxonomy", "common_names", "Common names", "; ".join(details["common_names"][:6]))
        add(NCBI, ncbi_version, "Taxonomy", "authority", "Authority", "; ".join(details["authority"][:3]))
        add(NCBI, ncbi_version, "Taxonomy", "division", "NCBI division", details["division"])
        add(NCBI, ncbi_version, "Taxonomy", "genetic_code", "Genetic code", details["genetic_code"])

    for key, found in (details.get("inferred") or {}).items():
        add(INFERRED, "NCBI lineage", "Virus traits", key, key.replace("_", " ").capitalize(), f"{found['value']} (from {found['basis']})")

    g = details.get("gtdb")

    if g:
        v = g.get("release", "")
        gl = " > ".join(c["name"] for c in gtdb_local.lineage_of(g))

        add(GTDB, v, "Taxonomy", "gtdb_lineage", "GTDB lineage", gl)
        add(GTDB, v, "Taxonomy", "gtdb_species", "GTDB species", g["name"])
        add(GTDB, v, "Species reference", "genomes", "Genomes of the species in GTDB", _number(g["genomes"]))
        add(GTDB, v, "Species reference", "genome_size", "Genome size, median (min - max)", f"{_number(g['genome_size_median'])} bp ({_number(g['genome_size_min'])} - {_number(g['genome_size_max'])})" if g.get("genome_size_median") else "")
        add(GTDB, v, "Species reference", "gc", "GC content, mean", f"{_number(g['gc_mean'], 1)} %" if g.get("gc_mean") is not None else "")
        add(GTDB, v, "Species reference", "completeness", "CheckM2 completeness, mean", f"{_number(g['completeness_mean'], 1)} %" if g.get("completeness_mean") is not None else "")
        add(GTDB, v, "Species reference", "contamination", "CheckM2 contamination, mean", f"{_number(g['contamination_mean'], 1)} %" if g.get("contamination_mean") is not None else "")
        add(GTDB, v, "Species reference", "type_material", "Genomes from type material", _number(g["type_material_genomes"]))
        add(GTDB, v, "Where it is found", "isolation_sources", "Common isolation sources", _pairs(g.get("isolation_sources")))
        add(GTDB, v, "Where it is found", "countries", "Countries", _pairs(g.get("countries")))

        r = g.get("representative_genome") or {}
        acc = g.get("representative", "")

        add(GTDB, v, "Reference genome", "rep_accession", "Representative genome", acc.split("_", 1)[-1] if acc else "")
        add(GTDB, v, "Reference genome", "rep_assembly_name", "Assembly name", r.get("assembly_name"))
        add(GTDB, v, "Reference genome", "rep_assembly_level", "Assembly level", r.get("assembly_level"))
        add(GTDB, v, "Reference genome", "rep_bioproject", "BioProject", r.get("bioproject"))
        add(GTDB, v, "Reference genome", "rep_biosample", "BioSample", r.get("biosample"))
        add(GTDB, v, "Reference genome", "rep_contigs", "Contigs", _number(r.get("contigs")))
        add(GTDB, v, "Reference genome", "rep_n50", "Contig N50", f"{_number(r.get('n50'))} bp" if r.get("n50") else "")
        add(GTDB, v, "Reference genome", "rep_proteins", "Annotated proteins", _number(r.get("proteins")))
        add(GTDB, v, "Reference genome", "rep_coding_density", "Coding density", f"{_number(r.get('coding_density'), 1)} %" if r.get("coding_density") else "")
        add(GTDB, v, "Reference genome", "rep_refseq_category", "RefSeq category", r.get("refseq_category"))
        add(GTDB, v, "Reference genome", "rep_strain", "Strain of the reference genome", r.get("strain") or r.get("isolate"))
        add(GTDB, v, "Reference genome", "rep_isolation_source", "Isolation source of the reference genome", r.get("isolation_source"))
        add(GTDB, v, "Reference genome", "rep_country", "Country of the reference genome", r.get("country"))

    return items


def main_details(sample):
    """The picked-taxon details of the sample's main organism, or None when it has none in a local database."""
    main = sample.organisms.filter(role=SampleOrganism.ROLE_PRIMARY).first()

    if main is None:
        return None, None

    if main.source == SampleOrganism.SOURCE_GTDB:
        return sample_organisms.details_gtdb(main.taxon_id), main

    if main.source == SampleOrganism.SOURCE_NCBI and main.taxon_id:
        return sample_organisms.details(main.taxon_id, sample.sample_type), main

    return None, main


def parse_selection(raw):
    if raw in (None, "", "[]"):
        return []

    import json

    try:
        rows = json.loads(raw)
    except ValueError:
        raise ValidationError("The reference metadata selection is not valid.")

    if not isinstance(rows, list) or len(rows) > MAX_ITEMS or not all(isinstance(r, dict) for r in rows):
        raise ValidationError("The reference metadata selection is not valid.")

    return [(str(r.get("source", "")), str(r.get("key", ""))) for r in rows]


@transaction.atomic
def attach(sample, selection, user=None):
    """Store the ticked items for the sample's main organism. Returns (added, unavailable)."""
    if not selection:
        return 0, 0

    details, main = main_details(sample)

    if details is None:
        return 0, len(selection)

    wanted = set(selection)
    available = {(i["source"], i["key"]): i for i in catalog(details)}
    added = 0

    for pair in wanted:
        item = available.get(pair)

        if item is None:
            continue

        SampleReferenceData.objects.update_or_create(
            sample=sample, source=item["source"], key=item["key"],
            defaults={
                "source_version": item["version"], "group": item["group"], "label": item["label"], "value": item["value"],
                "organism_name": main.name, "taxon_ref": main.taxon_id, "added_by": user,
            },
        )
        added += 1

    return added, len(wanted) - added


def remove(sample, ids):
    clean = [int(i) for i in ids if str(i).isdigit()]

    if clean:
        sample.reference_data.filter(pk__in=clean).delete()


def grouped(sample):
    """Attached items for the detail page, as a list of (group, [items])."""
    out = {}

    for item in sample.reference_data.all():
        out.setdefault(item.group or "Other", []).append(item)

    return sorted(out.items())
