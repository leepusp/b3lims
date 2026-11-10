"""Ready-made workflows: a network of steps with the instructions and the inputs each one needs.

Applying a template only creates ordinary steps and connections in the workflow, so everything can be edited afterwards.
Analysis steps are ``jupyter`` steps with starter parameters; choose or write the notebook, then run it from the card.
(A Galaxy tool can replace such a step when that connector exists.)
"""

from django.core.exceptions import ValidationError

from core.services import workflow as service


def _s(ref, title, kind="manual", notes="", params="", after=()):
    return {"ref": ref, "title": title, "kind": kind, "notes": notes, "parameters": params, "after": list(after)}


TEMPLATES = [
    {
        "key": "plasmid_verification", "name": "Plasmid verification", "category": "Molecular biology", "engine": "jupyter",
        "description": "Check a construct against its reference with sequencing reads.",
        "inputs": ["The reference plasmid (molecular record)", "Sequencing reads or consensus (FASTA/AB1)", "Minimum identity to accept"],
        "steps": [
            _s("ref", "Reference construct", notes="Link the plasmid record that should have been built."),
            _s("reads", "Sequencing data", notes="Attach or note where the reads/consensus are. Needed: FASTA or AB1 of every clone."),
            _s("align", "Align reads to reference", "jupyter", "Notebook reads the reference and reads, aligns them and lists mismatches.", "min_identity=99", ["ref", "reads"]),
            _s("review", "Review mismatches", notes="Decide per clone: accept, resequence or discard.", after=["align"]),
            _s("log", "Record the result", notes="Write the outcome in the ELN entry of the cloning.", after=["review"]),
        ],
    },
    {
        "key": "blast_search", "name": "BLAST similarity search", "category": "Sequence analysis", "engine": "jupyter",
        "description": "Search a sequence against a database and keep the best hits.",
        "inputs": ["Query sequence (molecular record)", "Database (for example nt, nr or a local one)", "E-value and identity thresholds"],
        "steps": [
            _s("query", "Query sequence", notes="Link the molecular record to search with."),
            _s("blast", "Run BLAST", "jupyter", "Needs the query and a database available on the cluster.", "db=nt\nevalue=1e-5", ["query"]),
            _s("filter", "Filter hits", "jupyter", "Keep hits by identity and coverage; write a table.", "min_identity=90\nmin_coverage=80", ["blast"]),
            _s("report", "Interpret", notes="Which organisms or genes are the best hits? What does it mean for the project?", after=["filter"]),
        ],
    },
    {
        "key": "alignment_tree", "name": "Alignment and phylogenetic tree", "category": "Sequence analysis", "engine": "jupyter",
        "description": "Align related sequences and draw a tree.",
        "inputs": ["Three or more homologous sequences (records or FASTA)", "Alignment method and substitution model"],
        "steps": [
            _s("seqs", "Collect sequences", notes="Link the records to compare; note the outgroup if any."),
            _s("msa", "Multiple alignment", "jupyter", "Aligns the sequences and writes the alignment.", "method=mafft", ["seqs"]),
            _s("tree", "Build the tree", "jupyter", "Builds and plots the tree from the alignment.", "model=GTR\nbootstrap=100", ["msa"]),
            _s("read", "Read the tree", notes="Describe the clades and support values.", after=["tree"]),
        ],
    },
    {
        "key": "table_pca", "name": "Table exploration and PCA", "category": "Data analysis", "engine": "jupyter",
        "description": "Clean a measurement table and look at its main components.",
        "inputs": ["A table (rows = samples, columns = variables)", "Which column holds the group labels"],
        "steps": [
            _s("table", "Input table", notes="Where is the table? Describe columns and units."),
            _s("qc", "Clean and normalise", "jupyter", "Remove empty rows, scale columns.", "group_column=group", ["table"]),
            _s("pca", "PCA", "jupyter", "Principal components, variance explained and a scatter plot.", "components=2", ["qc"]),
            _s("read", "Interpretation", notes="Which groups separate and which variables drive it?", after=["pca"]),
        ],
    },
    {
        "key": "genome_genbank", "name": "Assembled sequence to GenBank", "category": "Data submission", "engine": "jupyter", "submission": "genbank",
        "description": "From reads to an annotated sequence ready for the NCBI Submission Portal.",
        "inputs": ["Sample(s) and organism", "Raw reads (fastq) or an assembled sequence", "Annotation (genes/CDS) of the sequence", "Authors and BioProject, if any"],
        "steps": [
            _s("sample", "Sample and organism", notes="Link the sample; the organism sets the taxon of the package."),
            _s("qc", "Read quality control", "jupyter", "Needs the fastq files; reports quality and length.", "min_quality=20", ["sample"]),
            _s("asm", "Assembly", "jupyter", "Needs the filtered reads; writes the assembled sequence.", "min_length=200", ["qc"]),
            _s("ann", "Annotation", notes="Mark genes and CDS on the molecular record (they become the feature table).", after=["asm"]),
        ],
    },
    {
        "key": "reads_sra", "name": "Raw reads to SRA", "category": "Data submission", "engine": "manual", "submission": "genbank",
        "description": "Describe libraries and prepare the SRA metadata for sequencing runs.",
        "inputs": ["Samples (BioSample)", "Fastq/bam files, one or two per library", "Library strategy, source, selection, platform, instrument"],
        "steps": [
            _s("samples", "Samples", notes="Link every sample sequenced; the BioSample table is built from them."),
            _s("lib", "Library description", notes="Strategy, source, selection, layout, platform and instrument go in the package details.", after=["samples"]),
            _s("files", "Read files", notes="List the file names in the package (R1/R2 are paired automatically). Upload the files in the portal.", after=["lib"]),
        ],
    },
    {
        "key": "structure_pdb", "name": "Structure to wwPDB", "category": "Data submission", "engine": "manual", "submission": "pdb",
        "description": "From diffraction/cryo-EM data to a deposited structure.",
        "inputs": ["Refined coordinates (mmCIF)", "Structure factors or map", "Sequence of every entity", "Authors"],
        "steps": [
            _s("prot", "Protein and sample", notes="Link the molecular record and the sample used."),
            _s("data", "Experimental data", notes="Collection and processing; keep structure factors or maps ready for the portal.", after=["prot"]),
            _s("ref", "Refinement", notes="Final model in mmCIF; link the structure record.", after=["data"]),
            _s("val", "Validation", notes="Check the validation report of the portal before release.", after=["ref"]),
        ],
    },
    {
        "key": "dataset_zenodo", "name": "Dataset to Zenodo", "category": "Data submission", "engine": "manual", "submission": "zenodo",
        "description": "Publish a described dataset with a DOI.",
        "inputs": ["The files or records to publish", "A description and the authors", "A license"],
        "steps": [
            _s("collect", "Collect the data", notes="Link the records, entries or notebooks that belong in the dataset."),
            _s("describe", "Describe it", notes="Write the description, authors and license in the package.", after=["collect"]),
        ],
    },
]

BY_KEY = {t["key"]: t for t in TEMPLATES}


def catalog() -> list[dict]:
    """What the picker shows."""
    return [
        {
            "key": t["key"], "name": t["name"], "category": t["category"], "description": t["description"],
            "inputs": t["inputs"], "engine": t["engine"], "steps": [s["title"] for s in t["steps"]] + (["Data submission"] if t.get("submission") else []),
        }
        for t in TEMPLATES
    ]


def _levels(steps):
    level = {}

    for s in steps:  # steps are listed in flow order
        level[s["ref"]] = 1 + max((level[a] for a in s["after"]), default=-1)

    return level


def apply_template(workflow, user, key, x=40, y=40):
    template = BY_KEY.get(key)

    if not template:
        raise ValidationError("Unknown template.")

    extra = 1 if template.get("submission") else 0

    if workflow.steps.count() + len(template["steps"]) + extra > service.MAX_STEPS:
        raise ValidationError(f"At most {service.MAX_STEPS} steps per workflow.")

    level = _levels(template["steps"])
    row_in_level, created = {}, {}

    for spec in template["steps"]:
        col = level[spec["ref"]]
        row = row_in_level.get(col, 0)
        row_in_level[col] = row + 1
        data = {
            "title": spec["title"], "kind": spec["kind"], "notes": spec["notes"], "x": int(x) + col * 260, "y": int(y) + row * 150,
        }

        if spec["kind"] == "jupyter" and spec["parameters"]:
            data["parameters"] = spec["parameters"]

        created[spec["ref"]] = service.add_step(workflow, user, data)

    for spec in template["steps"]:
        for parent in spec["after"]:
            service.add_edge(workflow, created[parent].pk, created[spec["ref"]].pk)

    if extra:
        last = max(template["steps"], key=lambda s: level[s["ref"]])
        col = max(level.values()) + 1
        step, _package = service.add_submission_step(workflow, user, template["submission"], int(x) + col * 260, int(y))
        service.add_edge(workflow, created[last["ref"]].pk, step.pk)

    return list(created.values())
