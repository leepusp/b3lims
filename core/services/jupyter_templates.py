"""Starter Jupyter notebooks for common analyses.

Every template runs as it is, on small generated demo data, so it can be tried straight away; point its
parameters at real files to use it. Parameters are read with ``param()``, which takes the value injected by a
workflow run (always text) and falls back to the default, so the same notebook works by hand and unattended.
Only numpy, pandas and matplotlib are used.
"""

from copy import deepcopy

from core.services.jupyter_server import starter_notebook

PARAM_HELP = (
    "# Parameters: a workflow run replaces these values; edit the defaults to try the notebook by hand.\n"
    "def param(name, default):\n"
    "    value = globals().get(name, default)\n"
    "    try:\n"
    "        return type(default)(value)\n"
    "    except (TypeError, ValueError):\n"
    "        return default\n"
)

FASTA_HELP = '''import gzip, re

def open_text(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)

def read_fasta(path):
    records, name, parts = {}, None, []
    with open_text(path) as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if name is not None:
                    records[name] = "".join(parts).upper()
                name, parts = line[1:].split()[0], []
            elif line:
                parts.append(line)
    if name is not None:
        records[name] = "".join(parts).upper()
    return records

def align(a, b, match=1, mismatch=-1, gap=-2):
    """Global alignment (Needleman-Wunsch). Returns the two gapped strings."""
    n, m = len(a), len(b)
    score = np.zeros((n + 1, m + 1), dtype=np.int32)
    score[:, 0] = np.arange(n + 1) * gap
    score[0, :] = np.arange(m + 1) * gap
    for i in range(1, n + 1):
        ai = a[i - 1]
        for j in range(1, m + 1):
            diag = score[i - 1, j - 1] + (match if ai == b[j - 1] else mismatch)
            score[i, j] = max(diag, score[i - 1, j] + gap, score[i, j - 1] + gap)
    x, y, i, j = [], [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and score[i, j] == score[i - 1, j - 1] + (match if a[i - 1] == b[j - 1] else mismatch):
            x.append(a[i - 1]); y.append(b[j - 1]); i -= 1; j -= 1
        elif i > 0 and score[i, j] == score[i - 1, j] + gap:
            x.append(a[i - 1]); y.append("-"); i -= 1
        else:
            x.append("-"); y.append(b[j - 1]); j -= 1
    return "".join(reversed(x)), "".join(reversed(y))

def identity(x, y):
    pairs = [(p, q) for p, q in zip(x, y)]
    same = sum(1 for p, q in pairs if p == q and p != "-")
    return same / max(len(pairs), 1)
'''


def _cell(kind, source):
    cell = {"cell_type": kind, "metadata": {}, "source": source.strip("\n") + ("\n" if kind == "code" else "")}

    if kind == "code":
        cell.update({"execution_count": None, "outputs": []})

    return cell


def md(text):
    return _cell("markdown", text)


def code(text):
    return _cell("code", text)


SETUP = "import numpy as np\nimport pandas as pd\nimport matplotlib\nimport matplotlib.pyplot as plt\n\nrng = np.random.default_rng(7)\n"

TEMPLATES = {
    "pca_table": {
        "title": "PCA of a table",
        "category": "Data analysis",
        "description": "Clean a measurement table, standardise it and plot the first two principal components.",
        "parameters": {"input_path": "", "group_column": "group", "components": 2},
        "cells": [
            md("# PCA of a table\n\nRows are samples, columns are variables. Set `input_path` to a CSV/TSV file to use your own table; "
               "without it, a small generated table is used so you can see how the notebook works.\n\n"
               "**Needs:** a table with one row per sample, numeric columns and (optionally) a column with the group of each sample."),
            code(SETUP + "\n" + PARAM_HELP + "\ninput_path = param('input_path', '')\ngroup_column = param('group_column', 'group')\ncomponents = param('components', 2)"),
            md("## Load"),
            code("""if input_path:
    table = pd.read_csv(input_path, sep=None, engine="python")
else:
    groups = np.repeat(["control", "treated A", "treated B"], 12)
    shift = {"control": 0.0, "treated A": 2.0, "treated B": -2.0}
    table = pd.DataFrame({f"var{i}": rng.normal(0, 1, 36) + np.array([shift[g] * (i % 3 == 0) for g in groups]) for i in range(1, 7)})
    table[group_column] = groups
display(table.head())
print(table.shape[0], "rows,", table.shape[1], "columns")"""),
            md("## Clean and standardise"),
            code("""labels = table[group_column].astype(str) if group_column in table.columns else pd.Series(["all"] * len(table))
numeric = table.drop(columns=[group_column], errors="ignore").select_dtypes("number").dropna(axis=1, how="all")
keep = numeric.dropna().index
numeric, labels = numeric.loc[keep], labels.loc[keep]
scaled = (numeric - numeric.mean()) / numeric.std(ddof=0).replace(0, 1)
print(len(numeric), "samples and", numeric.shape[1], "variables kept")"""),
            md("## Principal components"),
            code("""u, s, vt = np.linalg.svd(scaled.values, full_matrices=False)
components = max(2, min(components, len(s)))
scores = pd.DataFrame(u[:, :components] * s[:components], columns=[f"PC{i + 1}" for i in range(components)], index=scaled.index)
explained = pd.DataFrame({"component": [f"PC{i + 1}" for i in range(len(s))], "variance_%": np.round(100 * s**2 / (s**2).sum(), 1)}).head(components)
display(explained)"""),
            code("""fig, ax = plt.subplots(figsize=(5.5, 4.5))
for name in sorted(labels.unique()):
    mask = (labels == name).values
    ax.scatter(scores.loc[mask, "PC1"], scores.loc[mask, "PC2"], label=name, s=36, alpha=.85)
ax.set_xlabel(f"PC1 ({explained['variance_%'][0]}%)")
ax.set_ylabel(f"PC2 ({explained['variance_%'][1]}%)")
ax.axhline(0, color="#ccc", lw=.8); ax.axvline(0, color="#ccc", lw=.8)
ax.legend(frameon=False)
ax.set_title("PCA")
plt.tight_layout()
plt.show()"""),
            md("## Which variables drive the separation?"),
            code("""loadings = pd.DataFrame(vt[:2].T, index=scaled.columns, columns=["PC1", "PC2"]).round(3)
display(loadings.reindex(loadings["PC1"].abs().sort_values(ascending=False).index).head(10))"""),
        ],
    },
    "sequence_stats": {
        "title": "Sequence statistics",
        "category": "Sequence analysis",
        "description": "Length, base composition, GC along the sequence and the longest open reading frames of a nucleotide sequence.",
        "parameters": {"fasta_path": "", "window": 60, "min_orf": 150},
        "cells": [
            md("# Sequence statistics\n\nSet `fasta_path` to a FASTA file (the first record is used). Without it a generated sequence is analysed.\n\n"
               "**Needs:** one nucleotide sequence."),
            code(SETUP + "\nimport re\n\n" + PARAM_HELP + "\nfasta_path = param('fasta_path', '')\nwindow = param('window', 60)\nmin_orf = param('min_orf', 150)\n" + FASTA_HELP),
            code("""if fasta_path:
    name, seq = next(iter(read_fasta(fasta_path).items()))
else:
    name = "demo"
    gene = "ATG" + "".join(rng.choice(list("ACGT"), 450)) + "TAA"
    seq = "".join(rng.choice(list("ACGT"), 300)) + gene + "".join(rng.choice(list("ACGT"), 300))
seq = re.sub("[^ACGTN]", "N", seq)
print(name, len(seq), "nt")"""),
            md("## Composition"),
            code("""counts = pd.Series(list(seq)).value_counts().reindex(list("ACGTN"), fill_value=0)
gc = 100 * (counts["G"] + counts["C"]) / max(len(seq) - counts["N"], 1)
display(pd.DataFrame({"base": counts.index, "count": counts.values, "percent": (100 * counts / len(seq)).round(1).values}))
print(f"Length {len(seq)} nt, GC {gc:.1f}%")"""),
            code("""bases = np.array(list(seq))
is_gc = np.isin(bases, ["G", "C"]).astype(float)
window = max(5, min(window, len(seq)))
rolling = np.convolve(is_gc, np.ones(window) / window, mode="valid") * 100
fig, ax = plt.subplots(figsize=(7, 3))
ax.plot(np.arange(len(rolling)) + window // 2, rolling, color="#0d6efd")
ax.axhline(gc, color="#999", ls="--", lw=.8)
ax.set_xlabel("position (nt)"); ax.set_ylabel("GC %")
ax.set_title(f"GC content, window {window} nt")
plt.tight_layout(); plt.show()"""),
            md("## Open reading frames (ATG to stop, both strands)"),
            code("""comp = str.maketrans("ACGTN", "TGCAN")
def orfs(s, strand):
    found = []
    for frame in range(3):
        start = None
        for i in range(frame, len(s) - 2, 3):
            codon = s[i:i + 3]
            if codon == "ATG" and start is None:
                start = i
            elif codon in ("TAA", "TAG", "TGA") and start is not None:
                if i + 3 - start >= min_orf:
                    found.append((strand, frame + 1, start + 1, i + 3, i + 3 - start))
                start = None
    return found
table = orfs(seq, "+") + orfs(seq.translate(comp)[::-1], "-")
result = pd.DataFrame(table, columns=["strand", "frame", "start", "end", "length_nt"]).sort_values("length_nt", ascending=False)
display(result.head(10))
print(len(result), "ORFs of at least", min_orf, "nt")"""),
        ],
    },
    "blast_hits": {
        "title": "Filter and summarise BLAST hits",
        "category": "Sequence analysis",
        "description": "Read a BLAST tabular result (outfmt 6), keep the good hits and summarise them.",
        "parameters": {"hits_path": "", "min_identity": 90, "min_length": 100, "max_evalue": 1e-5},
        "cells": [
            md("# BLAST hits\n\nRun BLAST on the cluster with `-outfmt 6` and set `hits_path` to the result file. Without it, generated hits are used.\n\n"
               "**Needs:** a BLAST tabular file (12 columns: qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore)."),
            code(SETUP + "\n" + PARAM_HELP + "\nhits_path = param('hits_path', '')\nmin_identity = param('min_identity', 90.0)\nmin_length = param('min_length', 100)\nmax_evalue = param('max_evalue', 1e-5)"),
            code("""columns = ["query", "subject", "identity", "length", "mismatch", "gapopen", "qstart", "qend", "sstart", "send", "evalue", "bitscore"]
if hits_path:
    hits = pd.read_csv(hits_path, sep="\\t", header=None, names=columns, comment="#")
else:
    subjects = ["Escherichia coli K-12", "Escherichia coli O157", "Shigella flexneri", "Salmonella enterica", "Klebsiella pneumoniae", "Bacillus subtilis"]
    hits = pd.DataFrame({
        "query": "query1", "subject": rng.choice(subjects, 60), "identity": np.round(rng.uniform(70, 100, 60), 1),
        "length": rng.integers(40, 900, 60), "mismatch": 0, "gapopen": 0, "qstart": 1, "qend": 900, "sstart": 1, "send": 900,
        "evalue": 10.0 ** -rng.uniform(0, 60, 60), "bitscore": np.round(rng.uniform(50, 1500, 60), 0),
    })
print(len(hits), "hits read")"""),
            md("## Filter"),
            code("""good = hits[(hits.identity >= min_identity) & (hits.length >= min_length) & (hits.evalue <= max_evalue)].sort_values("bitscore", ascending=False)
print(len(good), "hits pass: identity >=", min_identity, ", length >=", min_length, ", e-value <=", max_evalue)
display(good.head(10)[["query", "subject", "identity", "length", "evalue", "bitscore"]])"""),
            code("""summary = good.groupby("subject").agg(hits=("query", "size"), best_identity=("identity", "max"), best_bitscore=("bitscore", "max")).sort_values("best_bitscore", ascending=False)
display(summary.head(8))"""),
            code("""fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
axes[0].hist(hits.identity, bins=20, color="#adb5bd", label="all")
axes[0].hist(good.identity, bins=20, color="#0d6efd", label="kept")
axes[0].set_xlabel("identity %"); axes[0].legend(frameon=False)
top = summary.head(6)["hits"][::-1]
axes[1].barh(top.index, top.values, color="#198754")
axes[1].set_xlabel("hits kept")
plt.tight_layout(); plt.show()"""),
        ],
    },
    "alignment_tree": {
        "title": "Quick comparison and tree of sequences",
        "category": "Sequence analysis",
        "description": "Pairwise identities of a few related sequences and a UPGMA tree. A quick look, not a formal phylogeny.",
        "parameters": {"fasta_path": "", "max_length": 1200},
        "cells": [
            md("# Quick comparison and tree\n\nSet `fasta_path` to a FASTA file with 3 to 12 related sequences (up to `max_length` nt each). "
               "Without it, generated variants of one sequence are compared.\n\n"
               "**Needs:** three or more homologous nucleotide sequences. For publication use a proper aligner and phylogeny method."),
            code(SETUP + "\n" + PARAM_HELP + "\nfasta_path = param('fasta_path', '')\nmax_length = param('max_length', 1200)\n" + FASTA_HELP),
            code("""if fasta_path:
    records = {k: v[:max_length] for k, v in list(read_fasta(fasta_path).items())[:12]}
else:
    base = "".join(rng.choice(list("ACGT"), 300))
    def mutate(s, rate):
        return "".join(rng.choice(list("ACGT")) if rng.random() < rate else c for c in s)
    ancestor_a, ancestor_b = mutate(base, .05), mutate(base, .12)
    records = {"A1": mutate(ancestor_a, .01), "A2": mutate(ancestor_a, .02), "A3": mutate(ancestor_a, .03),
               "B1": mutate(ancestor_b, .01), "B2": mutate(ancestor_b, .02), "C1": mutate(base, .20)}
names = list(records)
print(len(names), "sequences:", ", ".join(names))"""),
            md("## Pairwise identity"),
            code("""n = len(names)
ident = np.eye(n)
for i in range(n):
    for j in range(i + 1, n):
        x, y = align(records[names[i]], records[names[j]])
        ident[i, j] = ident[j, i] = identity(x, y)
matrix = pd.DataFrame((ident * 100).round(1), index=names, columns=names)
display(matrix)"""),
            md("## UPGMA tree"),
            code("""dist = {i: {j: 1 - ident[i, j] for j in range(n) if j != i} for i in range(n)}
clusters = {i: (names[i], 0.0, 1) for i in range(n)}   # id -> (label, height, size)
tree = {i: (names[i], None, None, 0.0) for i in range(n)}
next_id = n
while len(clusters) > 1:
    a, b = min(((i, j) for i in clusters for j in clusters if i < j), key=lambda p: dist[p[0]][p[1]])
    height = dist[a][b] / 2
    size = clusters[a][2] + clusters[b][2]
    new = next_id; next_id += 1
    tree[new] = (None, a, b, height)
    dist[new] = {}
    for c in list(clusters):
        if c in (a, b):
            continue
        d = (dist[a][c] * clusters[a][2] + dist[b][c] * clusters[b][2]) / size
        dist[new][c] = dist[c][new] = d
    clusters = {k: v for k, v in clusters.items() if k not in (a, b)}
    clusters[new] = (None, height, size)
root = next(iter(clusters))

order = []
def leaves(node):
    label, left, right, _ = tree[node]
    if left is None:
        order.append(node); return
    leaves(left); leaves(right)
leaves(root)
ypos = {leaf: i for i, leaf in enumerate(order)}

def draw(node, ax):
    label, left, right, height = tree[node]
    if left is None:
        return ypos[node], 0.0
    yl, hl = draw(left, ax)
    yr, hr = draw(right, ax)
    ax.plot([hl, height, height, hr], [yl, yl, yr, yr], color="#495057", lw=1.4)
    return (yl + yr) / 2, height

fig, ax = plt.subplots(figsize=(6, 0.5 * n + 1.2))
draw(root, ax)
for leaf, y in ypos.items():
    ax.text(-0.002, y, tree[leaf][0], ha="right", va="center", fontsize=9)
ax.set_yticks([]); ax.invert_xaxis()
ax.set_xlabel("distance (1 - identity)")
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.set_title("UPGMA tree")
plt.tight_layout(); plt.show()"""),
        ],
    },
    "read_qc": {
        "title": "Sequencing reads quality control",
        "category": "Sequencing",
        "description": "Read lengths, quality per position and the share of good reads in a FASTQ file.",
        "parameters": {"fastq_path": "", "min_quality": 20, "max_reads": 50000},
        "cells": [
            md("# Reads quality control\n\nSet `fastq_path` to a FASTQ file (plain or `.gz`). Without it, generated reads are used.\n\n"
               "**Needs:** a FASTQ file; only the first `max_reads` reads are read."),
            code(SETUP + "\nimport gzip\n\n" + PARAM_HELP + "\nfastq_path = param('fastq_path', '')\nmin_quality = param('min_quality', 20)\nmax_reads = param('max_reads', 50000)"),
            code("""reads = []
if fastq_path:
    handle = gzip.open(fastq_path, "rt") if fastq_path.endswith(".gz") else open(fastq_path)
    with handle:
        while len(reads) < max_reads:
            header, seq, plus, qual = (handle.readline().rstrip() for _ in range(4))
            if not qual:
                break
            reads.append((seq, np.frombuffer(qual.encode(), dtype=np.uint8).astype(int) - 33))
else:
    for _ in range(2000):
        length = int(rng.integers(120, 151))
        seq = "".join(rng.choice(list("ACGT"), length))
        quality = np.clip(rng.normal(36, 3, length) - np.linspace(0, 14, length) + rng.normal(0, 2, length), 2, 41).astype(int)
        reads.append((seq, quality))
print(len(reads), "reads")"""),
            md("## Summary"),
            code("""lengths = np.array([len(s) for s, _ in reads])
mean_q = np.array([q.mean() for _, q in reads])
gc = np.array([(s.count("G") + s.count("C")) / max(len(s), 1) for s, _ in reads])
display(pd.DataFrame({
    "reads": [len(reads)], "mean_length": [round(lengths.mean(), 1)], "min_length": [lengths.min()], "max_length": [lengths.max()],
    "mean_quality": [round(mean_q.mean(), 1)], f"reads_Q>={min_quality}_%": [round(100 * (mean_q >= min_quality).mean(), 1)], "GC_%": [round(100 * gc.mean(), 1)],
}))"""),
            code("""longest = lengths.max()
padded = np.full((len(reads), longest), np.nan)
for i, (_, q) in enumerate(reads):
    padded[i, :len(q)] = q
fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
axes[0].plot(np.nanmean(padded, axis=0), color="#0d6efd")
axes[0].fill_between(range(longest), np.nanpercentile(padded, 10, axis=0), np.nanpercentile(padded, 90, axis=0), alpha=.2)
axes[0].axhline(min_quality, color="#dc3545", ls="--", lw=.8)
axes[0].set_xlabel("position"); axes[0].set_ylabel("quality"); axes[0].set_title("Quality per position")
axes[1].hist(lengths, bins=20, color="#6c757d"); axes[1].set_xlabel("read length"); axes[1].set_title("Lengths")
axes[2].hist(mean_q, bins=20, color="#198754"); axes[2].axvline(min_quality, color="#dc3545", ls="--", lw=.8)
axes[2].set_xlabel("mean read quality"); axes[2].set_title("Read quality")
plt.tight_layout(); plt.show()"""),
        ],
    },
    "plasmid_verification": {
        "title": "Verify a plasmid against its reference",
        "category": "Molecular biology",
        "description": "Align a sequenced consensus to the reference and list every difference.",
        "parameters": {"reference_path": "", "consensus_path": "", "min_identity": 99.0},
        "cells": [
            md("# Plasmid verification\n\nSet `reference_path` and `consensus_path` to FASTA files (the first record of each). "
               "Without them a generated pair with a few differences is compared.\n\n"
               "**Needs:** the reference sequence of the construct and the consensus of your sequencing reads (up to about 3000 nt)."),
            code(SETUP + "\n" + PARAM_HELP + "\nreference_path = param('reference_path', '')\nconsensus_path = param('consensus_path', '')\nmin_identity = param('min_identity', 99.0)\n" + FASTA_HELP),
            code("""if reference_path and consensus_path:
    ref_name, reference = next(iter(read_fasta(reference_path).items()))
    cons_name, consensus = next(iter(read_fasta(consensus_path).items()))
else:
    ref_name, cons_name = "reference", "consensus"
    reference = "".join(rng.choice(list("ACGT"), 700))
    consensus = list(reference)
    for pos in (120, 410):
        consensus[pos] = "A" if consensus[pos] != "A" else "C"
    del consensus[560]
    consensus = "".join(consensus)
print(ref_name, len(reference), "nt;", cons_name, len(consensus), "nt")
if len(reference) * len(consensus) > 9_000_000:
    raise ValueError("Sequences are too long for this notebook (use up to about 3000 nt).")"""),
            md("## Alignment"),
            code("""x, y = align(reference, consensus)
pct = 100 * identity(x, y)
print(f"Identity {pct:.2f}% over {len(x)} aligned columns")"""),
            code("""diffs, ref_pos = [], 0
for a, b in zip(x, y):
    if a != "-":
        ref_pos += 1
    if a != b:
        kind = "insertion in consensus" if a == "-" else "deletion in consensus" if b == "-" else "substitution"
        diffs.append({"reference_position": ref_pos, "reference": a, "consensus": b, "type": kind})
differences = pd.DataFrame(diffs, columns=["reference_position", "reference", "consensus", "type"])
display(differences)
print("Verdict:", "PASS" if pct >= min_identity else "CHECK", f"(threshold {min_identity}% identity)")"""),
            code("""fig, ax = plt.subplots(figsize=(8, 1.6))
ax.hlines(0, 0, len(reference), color="#adb5bd", lw=6)
if len(differences):
    ax.scatter(differences.reference_position, np.zeros(len(differences)), color="#dc3545", zorder=3, s=40)
ax.set_yticks([]); ax.set_xlabel("position in the reference (nt)")
ax.set_title(f"{len(differences)} differences")
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
plt.tight_layout(); plt.show()"""),
        ],
    },
}


def catalog() -> list[dict]:
    return [
        {"key": key, "title": t["title"], "category": t["category"], "description": t["description"], "parameters": dict(t["parameters"])}
        for key, t in TEMPLATES.items()
    ]


def build(key, owner_name="") -> dict:
    """The nbformat document of a template."""
    template = TEMPLATES[key]
    document = starter_notebook(template["title"], owner_name)
    document["cells"] = deepcopy(template["cells"])
    document["metadata"]["biobank"]["template"] = key
    document["metadata"]["biobank"]["parameters"] = dict(template["parameters"])

    return document


def create_notebook(user, key):
    from django.core.exceptions import ValidationError

    from core.models.lab_tools.notebook import JupyterNotebook

    if key not in TEMPLATES:
        raise ValidationError("Unknown notebook template.")

    template = TEMPLATES[key]

    return JupyterNotebook.objects.create(
        title=template["title"], description=template["description"], owner=user, updated_by=user,
        notebook_json=build(key, user.get_username()),
    )
