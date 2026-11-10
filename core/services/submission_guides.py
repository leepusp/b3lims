"""What each submission destination needs, and how far a package is from having it.

The checklist is advice built from the same rules as ``submission_adapters.validate``; it never blocks anything.
Each requirement is ``met`` True/False, or None when it cannot be checked here (done in the portal).
"""

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
        nodes.append({"key": "accession", "title": "Record the reference", "detail": "Accession, PDB id or DOI", "done": bool(package.external_reference)})

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
    }

