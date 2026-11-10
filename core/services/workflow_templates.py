"""Ready-made workflows: a network of steps with the instructions and the inputs each one needs.

Applying a template only creates ordinary steps and connections in the workflow, so everything can be edited afterwards.
Analysis steps are ``jupyter`` steps with starter parameters; choose or write the notebook, then run it from the card.
(A Galaxy tool can replace such a step when that connector exists.)
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.services import workflow as service


def _s(ref, title, kind="manual", notes="", params="", after=(), notebook="", galaxy=""):
    return {"ref": ref, "title": title, "kind": kind, "notes": notes, "parameters": params, "after": list(after), "notebook": notebook, "galaxy": galaxy}


TS = "toolshed.g2.bx.psu.edu/repos/"


TEMPLATES = [
    {
        "key": "plasmid_verification", "name": "Plasmid verification", "category": "Molecular biology", "engine": "jupyter",
        "description": "Check a construct against its reference with sequencing reads.",
        "inputs": ["The reference plasmid (FASTA)", "The sequencing consensus (FASTA)", "Minimum identity to accept"],
        "steps": [
            _s("ref", "Reference construct", notes="Link the plasmid record that should have been built, and export its FASTA."),
            _s("reads", "Sequencing data", notes="Attach or note where the reads/consensus are. Needed: the consensus FASTA of every clone."),
            _s("align", "Align consensus to reference", "jupyter", "Set reference_path and consensus_path to the FASTA files. Without them the notebook runs on demo data.", after=["ref", "reads"], notebook="plasmid_verification"),
            _s("review", "Review differences", notes="Decide per clone: accept, resequence or discard.", after=["align"]),
            _s("log", "Record the result", notes="Write the outcome in the ELN entry of the cloning.", after=["review"]),
        ],
    },
    {
        "key": "blast_search", "name": "BLAST similarity search", "category": "Sequence analysis", "engine": "jupyter",
        "description": "Search a sequence against a database and keep the best hits.",
        "inputs": ["Query sequence (FASTA)", "A BLAST database on the cluster", "E-value, identity and length thresholds"],
        "steps": [
            _s("query", "Query sequence", notes="Link the molecular record to search with."),
            _s("blast", "Run BLAST", notes="On the cluster: blastn -query query.fasta -db <database> -outfmt 6 -out hits.tsv. Keep hits.tsv where the next step can read it.", after=["query"]),
            _s("filter", "Filter and summarise hits", "jupyter", "Set hits_path to hits.tsv. Without it the notebook runs on demo hits.", after=["blast"], notebook="blast_hits"),
            _s("report", "Interpret", notes="Which organisms or genes are the best hits? What does it mean for the project?", after=["filter"]),
        ],
    },
    {
        "key": "alignment_tree", "name": "Compare sequences and draw a tree", "category": "Sequence analysis", "engine": "jupyter",
        "description": "Pairwise identities of related sequences and a quick UPGMA tree.",
        "inputs": ["Three or more homologous sequences in one FASTA file"],
        "steps": [
            _s("seqs", "Collect sequences", notes="Link the records to compare and gather them in one FASTA file; note the outgroup if any."),
            _s("tree", "Identity matrix and tree", "jupyter", "Set fasta_path. For a formal phylogeny use a dedicated aligner and tree method.", after=["seqs"], notebook="alignment_tree"),
            _s("read", "Read the tree", notes="Describe the clades and how close the sequences are.", after=["tree"]),
        ],
    },
    {
        "key": "table_pca", "name": "Table exploration and PCA", "category": "Data analysis", "engine": "jupyter",
        "description": "Clean a measurement table and look at its main components.",
        "inputs": ["A table (rows = samples, columns = variables)", "Which column holds the group labels"],
        "steps": [
            _s("table", "Input table", notes="Where is the table? Describe columns and units."),
            _s("pca", "Clean, standardise and PCA", "jupyter", "Set input_path to the CSV/TSV and group_column to the label column.", after=["table"], notebook="pca_table"),
            _s("read", "Interpretation", notes="Which groups separate and which variables drive it?", after=["pca"]),
        ],
    },
    {
        "key": "genome_genbank", "name": "Assembled sequence to GenBank", "category": "Data submission", "engine": "jupyter", "submission": "genbank",
        "description": "From reads to an annotated sequence ready for the NCBI Submission Portal.",
        "inputs": ["Sample(s) and organism", "Raw reads (fastq) or an assembled sequence", "Annotation (genes/CDS) of the sequence", "Authors and BioProject, if any"],
        "steps": [
            _s("sample", "Sample and organism", notes="Link the sample; the organism sets the taxon of the package."),
            _s("qc", "Read quality control", "jupyter", "Set fastq_path to the reads (plain or .gz).", after=["sample"], notebook="read_qc"),
            _s("asm", "Assembly", notes="Assemble with your tool on the cluster and register the result as a molecular record (it goes into the package).", after=["qc"]),
            _s("stats", "Sequence statistics", "jupyter", "Set fasta_path to the assembled sequence.", after=["asm"], notebook="sequence_stats"),
            _s("ann", "Annotation", notes="Mark genes and CDS on the molecular record (they become the feature table).", after=["stats"]),
        ],
    },
    {
        "key": "reads_sra", "name": "Raw reads to SRA", "category": "Data submission", "engine": "jupyter", "submission": "genbank",
        "description": "Describe libraries and prepare the SRA metadata for sequencing runs.",
        "inputs": ["Samples (BioSample)", "Fastq/bam files, one or two per library", "Library strategy, source, selection, platform, instrument"],
        "steps": [
            _s("samples", "Samples", notes="Link every sample sequenced; the BioSample table is built from them."),
            _s("qc", "Read quality control", "jupyter", "Set fastq_path to one of the files to check its quality before submitting.", after=["samples"], notebook="read_qc"),
            _s("lib", "Library description", notes="Strategy, source, selection, layout, platform and instrument go in the package details.", after=["qc"]),
            _s("files", "Read files", notes="List the file names in the package (R1/R2 are paired automatically). Upload the files in the portal.", after=["lib"]),
        ],
    },
    {
        "key": "galaxy_genome_annotation", "name": "Reads to annotated genome (Galaxy)", "category": "Galaxy", "engine": "galaxy", "submission": "genbank",
        "description": "Quality control, trimming, assembly check and Bakta annotation with the lab's Galaxy tools, then a GenBank package.",
        "inputs": ["Raw reads (fastq) available to Galaxy", "An assembler of your choice for the assembly step", "Sample and organism"],
        "steps": [
            _s("sample", "Sample and organism", notes="Link the sample; the organism sets the taxon of the package."),
            _s("qc", "FastQC", "galaxy", "Run in Galaxy on your reads; note the verdict in the result note.", after=["sample"], galaxy=TS + "devteam/fastqc/fastqc"),
            _s("trim", "Trimmomatic", "galaxy", "Trim adapters and low-quality ends.", after=["qc"], galaxy=TS + "pjbriggs/trimmomatic/trimmomatic"),
            _s("asm", "Assembly", notes="Assemble with the tool you prefer on the cluster, and register the result as a molecular record.", after=["trim"]),
            _s("quast", "QUAST", "galaxy", "Assembly statistics: N50, total length, contigs.", after=["asm"], galaxy=TS + "iuc/quast/quast"),
            _s("bakta", "Bakta", "galaxy", "Annotate the assembly; bring the annotation back to the molecular record.", after=["quast"], galaxy="davinci_bakta"),
        ],
    },
    {
        "key": "galaxy_align_tree", "name": "Align and build a tree (Galaxy)", "category": "Galaxy", "engine": "galaxy",
        "description": "MAFFT alignment, trimAl trimming and an IQ-TREE maximum-likelihood tree.",
        "inputs": ["Homologous sequences in one FASTA file, uploaded to Galaxy"],
        "steps": [
            _s("seqs", "Collect sequences", notes="Gather the sequences in one FASTA file and upload it to Galaxy."),
            _s("mafft", "MAFFT", "galaxy", "Multiple alignment.", after=["seqs"], galaxy=TS + "rnateam/mafft/rbc_mafft"),
            _s("trimal", "trimAl", "galaxy", "Remove poorly aligned columns.", after=["mafft"], galaxy=TS + "iuc/trimal/trimal"),
            _s("iqtree", "IQ-TREE", "galaxy", "Maximum-likelihood tree with bootstrap support.", after=["trimal"], galaxy=TS + "iuc/iqtree/iqtree"),
            _s("read", "Read the tree", notes="Describe the clades and support values.", after=["iqtree"]),
        ],
    },
    {
        "key": "galaxy_map_variants", "name": "Map reads and call variants (Galaxy)", "category": "Galaxy", "engine": "galaxy",
        "description": "Quality control, BWA-MEM mapping and FreeBayes variant calling.",
        "inputs": ["Reads (fastq)", "A reference genome in FASTA", "Samples and organism"],
        "steps": [
            _s("sample", "Sample and reference", notes="Link the sample and the reference molecular record."),
            _s("qc", "FastQC", "galaxy", "Check the reads first.", after=["sample"], galaxy=TS + "devteam/fastqc/fastqc"),
            _s("map", "BWA-MEM", "galaxy", "Map the reads to the reference.", after=["qc"], galaxy=TS + "devteam/bwa/bwa_mem"),
            _s("call", "FreeBayes", "galaxy", "Call variants from the mapping.", after=["map"], galaxy=TS + "devteam/freebayes/freebayes"),
            _s("read", "Review the variants", notes="Filter and interpret; note the ones that matter.", after=["call"]),
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


def _workflow_entries() -> list[dict]:
    return [
        {
            "key": t["key"], "name": t["name"], "category": t["category"], "description": t["description"],
            "inputs": t["inputs"], "engine": t["engine"], "steps": [s["title"] for s in t["steps"]] + (["Data submission"] if t.get("submission") else []),
        }
        for t in TEMPLATES
    ]


def block_entries() -> list[dict]:
    """Single steps that can be added on their own: a task, a note, one analysis notebook or one submission."""
    from core.models.lab_tools.submission import SubmissionPackage
    from core.services import jupyter_templates

    blocks = [
        {"key": "manual", "name": "Task", "category": "Basic", "description": "A step done by hand: assign it, give it a due date and link records."},
        {"key": "note", "name": "Note", "category": "Basic", "description": "A free annotation on the canvas, with images and tables."},
    ]
    blocks += [
        {"key": f"notebook:{key}", "name": t["title"], "category": f"Analysis: {t['category']}", "description": t["description"] + " Creates its own notebook."}
        for key, t in jupyter_templates.TEMPLATES.items()
    ]
    blocks += [
        {"key": f"submission:{value}", "name": f"Data submission: {label.split(' (')[0]}", "category": "Data submission",
         "description": "A draft submission package for this destination, filled with what the workflow links."}
        for value, label in SubmissionPackage.Destination.choices
    ]

    return blocks


def catalog() -> dict:
    """What the picker shows: whole workflows and single steps."""
    return {"workflows": _workflow_entries(), "blocks": block_entries()}


def add_block(workflow, user, key, x=40, y=40):
    """Add one step from the catalog; returns the new step."""
    from core.services import jupyter_templates

    kind, _, ref = (key or "").partition(":")

    if kind in ("manual", "note") and not ref:
        return service.add_step(workflow, user, {"title": "Note" if kind == "note" else "New step", "kind": kind, "x": int(x), "y": int(y)})
    if kind == "notebook" and ref in jupyter_templates.TEMPLATES:
        template = jupyter_templates.TEMPLATES[ref]

        with transaction.atomic():
            notebook = jupyter_templates.create_notebook(user, ref)

            return service.add_step(workflow, user, {
                "title": template["title"], "kind": "jupyter", "jupyter_notebook": notebook.pk, "x": int(x), "y": int(y),
                "parameters": "\n".join(f"{k}={v}" for k, v in template["parameters"].items()),
            })
    if kind == "submission":
        return service.add_submission_step(workflow, user, ref, int(x), int(y))[0]

    raise ValidationError("Unknown step.")


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

    with transaction.atomic():
        return _build(workflow, user, template, extra, x, y)


def _build(workflow, user, template, extra, x, y):
    level = _levels(template["steps"])
    row_in_level, created = {}, {}

    for spec in template["steps"]:
        col = level[spec["ref"]]
        row = row_in_level.get(col, 0)
        row_in_level[col] = row + 1
        data = {
            "title": spec["title"], "kind": spec["kind"], "notes": spec["notes"], "x": int(x) + col * 260, "y": int(y) + row * 150,
        }

        if spec["kind"] == "galaxy":
            from core.services import galaxy

            tool = galaxy.resolve_tool(spec["galaxy"])

            if tool:
                step = service.add_galaxy_step(workflow, user, tool, data["x"], data["y"])
                step.title, step.notes = spec["title"], spec["notes"]
                step.save(update_fields=["title", "notes"])
                created[spec["ref"]] = step
                continue

            data["kind"] = "manual"
            data["notes"] = f"{spec['notes']} (Galaxy tool: {spec['galaxy'].rsplit('/', 1)[-1]}; it was not found in the Galaxy catalog just now, so this is a plain step.)"
        if spec["kind"] == "jupyter":
            from core.services import jupyter_templates

            if spec["notebook"]:
                notebook = jupyter_templates.create_notebook(user, spec["notebook"])
                defaults = jupyter_templates.TEMPLATES[spec["notebook"]]["parameters"]
                data["jupyter_notebook"] = notebook.pk
                data["parameters"] = "\n".join(f"{k}={v}" for k, v in defaults.items())
            elif spec["parameters"]:
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
