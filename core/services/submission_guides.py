"""What each submission destination needs, and how far a package is from having it.

The checklist is advice built from the same rules as ``submission_adapters.validate``; it never blocks anything.
Each requirement is ``met`` True/False, or None when it cannot be checked here (done in the portal).
"""

import re

from core.services import submission_adapters as adapters

D = adapters.D

PORTALS = {
    D.INTERNAL: "",
    D.GENBANK: "https://submit.ncbi.nlm.nih.gov/",
    D.PDB: "https://deposit-pdbe.wwpdb.org/deposition",
    D.ZENODO: "https://zenodo.org/uploads/new",
}

SUMMARY = {
    D.INTERNAL: "Keeps a reviewed, citable copy in the lab repository (manifest, RO-Crate and the files).",
    D.GENBANK: "Nucleotide sequences go to GenBank through the NCBI Submission Portal; raw reads go to SRA. "
    "This tool prepares the FASTA, feature table and metadata tables; the upload happens in the portal.",
    D.PDB: "Structures are deposited in the wwPDB deposition service (mmCIF preferred). This tool prepares the "
    "coordinates and the description; experimental data and validation are added in the portal.",
    D.ZENODO: "Files and a description become a Zenodo record with a DOI. A draft can be created here when a token is configured.",
}


NCBI = "https://www.ncbi.nlm.nih.gov"
# (kind label, pattern, url template) per destination; first match wins.
REFERENCE_RULES = {
    D.GENBANK: (
        ("GenBank accession", r"(?:[A-Z]{1,2}\d{5,6}|[A-Z]{4,6}\d{8,10})(?:\.\d+)?", NCBI + "/nuccore/{}"),
        ("SRA run", r"[SED]RR\d{5,}", NCBI + "/sra/{}"),
        ("SRA experiment", r"[SED]RX\d{5,}", NCBI + "/sra/{}"),
        ("BioProject", r"PRJ[NED][A-Z]\d+", NCBI + "/bioproject/{}"),
        ("BioSample", r"SAM[NED][A-Z]?\d+", NCBI + "/biosample/{}"),
    ),
    D.PDB: (
        ("PDB id", r"(?:pdb_0000)?(?=[0-9]*[A-Za-z])[0-9][A-Za-z0-9]{3}", "https://www.rcsb.org/structure/{}"),
        ("EMDB map", r"EMD-\d{4,5}", "https://www.ebi.ac.uk/emdb/{}"),
    ),
    D.ZENODO: (
        ("DOI", r"10\.5281/zenodo\.\d+", "https://doi.org/{}"),
    ),
}
URL = re.compile(r"^https?://[^\s<>\"']{4,290}$")


def references(package) -> list[dict]:
    """The accessions/ids/DOIs typed as the reference of an external submission, recognised and linked.

    ``package.external_reference`` may hold several, separated by spaces, commas or lines.
    """
    raw = package.external_reference or ""
    found = []

    for token in dict.fromkeys(t for t in re.split(r"[\s,;]+", raw) if t):
        entry = {"text": token, "kind": "", "url": "", "valid": False}

        for label, pattern, template in REFERENCE_RULES.get(package.destination, ()):
            if re.fullmatch(pattern, token):
                entry.update(kind=label, url=template.format(token), valid=True)
                break
        else:
            if URL.match(token) and package.destination != D.INTERNAL:
                entry.update(kind="Link", url=token, valid=True)

        found.append(entry)

    return found


def _nucleotide(package):
    return [
        i for i in package.items.filter(kind="sequence").select_related("molecule")
        if i.molecule and i.molecule.sequence_type in adapters.NUCLEOTIDE_TYPES
    ]


def _meta(package, *keys):
    meta = package.metadata or {}

    return all(meta.get(k) for k in keys)


def _req(key, kind, title, detail, met, required=True):
    return {"key": key, "kind": kind, "title": title, "detail": detail, "met": met, "required": required}


def _records(package):
    return package.items.exists()


def _requirements(package):
    dest = package.destination
    items = package.items
    taxon = bool(package.taxon_id)

    if dest == D.GENBANK:
        nucleotide = _nucleotide(package)
        reads = bool(adapters._reads(package))
        sra_keys = ("sra_strategy", "sra_source", "sra_selection", "sra_platform", "sra_instrument")

        return [
            _req("sequences", "data", "Nucleotide sequence records", "DNA/RNA/plasmid records, 200 nt or longer. Written as sequences.fasta.",
                 bool(nucleotide) or reads),
            _req("organism", "metadata", "Source organism", "Choose the taxon; it goes into every FASTA header.", taxon),
            _req("features", "data", "Annotations (optional)", "Genes, CDS and other features of the records become features.tbl.",
                 any(i.molecule.features.exists() for i in nucleotide), required=False),
            _req("authors", "metadata", "Authors", "Needed for the submission template in the portal.", _meta(package, "authors")),
            _req("bioproject", "metadata", "BioProject / BioSample", "Accessions if they already exist; otherwise the portal creates them.",
                 _meta(package, "bioproject", "biosample"), required=False),
            _req("reads", "file", "Raw reads for SRA (optional)", "Fastq/bam file names, plus the library fields below. The files are uploaded in the portal.",
                 reads, required=False),
            _req("library", "metadata", "SRA library description", "Strategy, source, selection, platform and instrument model.",
                 _meta(package, *sra_keys) if reads else None, required=reads),
        ]
    if dest == D.PDB:
        structures = items.filter(kind="structure").exists()

        return [
            _req("structure", "data", "3D structure record", "Coordinates in mmCIF (PDB format is accepted but not preferred).", structures),
            _req("organism", "metadata", "Source organism", "The deposition asks for it.", taxon, required=False),
            _req("authors", "metadata", "Authors", "Required by the deposition.", _meta(package, "authors")),
            _req("experiment", "file", "Experimental data", "Structure factors, maps or restraints. Uploaded in the deposition portal.", None, required=False),
            _req("validation", "file", "Validation report", "Produced by the portal after upload; review it before releasing.", None, required=False),
        ]
    if dest == D.ZENODO:
        return [
            _req("records", "data", "Something to publish", "Records of this package are exported as files.", _records(package)),
            _req("description", "metadata", "Description", "Zenodo requires one.", bool(package.description.strip())),
            _req("authors", "metadata", "Authors", "Creators of the record.", _meta(package, "authors"), required=False),
            _req("license", "metadata", "License", "CC BY 4.0 is proposed when none is given.", _meta(package, "license"), required=False),
        ]

    return [
        _req("records", "data", "Records", "Anything from the lab: sequences, structures, samples, entries, notebooks.", _records(package)),
        _req("taxon", "metadata", "Taxon (optional)", "Makes the package findable by organism.", taxon, required=False),
        _req("description", "metadata", "Description (optional)", "What the package is and how it was made.", bool(package.description.strip()), required=False),
    ]


def _flow(package, requirements, validation):
    required_met = all(r["met"] for r in requirements if r["required"] and r["met"] is not None)
    status = package.status
    external = package.destination != D.INTERNAL
    published = status == "published"

    nodes = [
        {"key": "data", "title": "Gather data", "detail": "Records, samples and their data", "done": any(
            r["met"] for r in requirements if r["kind"] == "data"
        ) or _records(package)},
        {"key": "describe", "title": "Describe", "detail": "Organism, authors, details", "done": required_met},
        {"key": "check", "title": "Check", "detail": "No errors", "done": not validation["errors"] and _records(package)},
        {"key": "review", "title": "Review", "detail": "An approver signs off", "done": status in ("approved", "published")},
        {"key": "files", "title": "Prepare files", "detail": "Repository folder + manifest", "done": published},
    ]

    if external:
        nodes.append({"key": "portal", "title": "Submit in the portal", "detail": "Upload the prepared files", "done": bool(package.external_reference)})
        nodes.append({"key": "accession", "title": "Record the reference", "detail": "Accession, PDB id or DOI", "done": any(r["valid"] for r in references(package))})

    first_open = next((n for n in nodes if not n["done"]), None)

    for n in nodes:
        n["state"] = "done" if n["done"] else "current" if n is first_open else "todo"

    return nodes


def guide(package, validation=None) -> dict:
    validation = validation or adapters.validate(package)
    requirements = _requirements(package)

    try:
        outputs = sorted(adapters.destination_files(package))
    except Exception:  # a half-filled package can fail to render; the checklist should still show
        outputs = []

    return {
        "destination": package.destination,
        "summary": SUMMARY.get(package.destination, SUMMARY[D.INTERNAL]),
        "portal": PORTALS.get(package.destination, ""),
        "requirements": requirements,
        "flow": _flow(package, requirements, validation),
        "outputs": outputs,
        "references": references(package),
    }

