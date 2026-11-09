"""Per-destination checks and files for data submissions.

Every destination gets the common package files (see ``repository``) plus its own
folder with files shaped for that service and a README with the manual steps.
Nothing here talks to a network service except ``upload_zenodo_draft``, which
only ever creates a draft.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ValidationError

from core.models.lab_tools.submission import SubmissionPackage

D = SubmissionPackage.Destination
NUCLEOTIDE = re.compile(r"^[ACGTUNRYSWKMBDHV\-]+$")
NUCLEOTIDE_TYPES = ("dna", "rna", "plasmid", "primer")
GENBANK_MIN_LENGTH = 200
CC_LICENSES = {
    "creativecommons.org/licenses/by/4.0": "cc-by-4.0",
    "creativecommons.org/licenses/by-sa/4.0": "cc-by-sa-4.0",
    "creativecommons.org/licenses/by-nc/4.0": "cc-by-nc-4.0",
    "creativecommons.org/publicdomain/zero/1.0": "cc0-1.0",
}


def _items(package, kind):
    return [i for i in package.items.select_related("molecule", "structure", "structure__molecule") if i.kind == kind]


def _authors(package) -> list[str]:
    raw = (package.metadata or {}).get("authors", "")
    names = [a.strip() for a in re.split(r"[;\n]", raw) if a.strip()]

    return names


def _seq_id(name: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "seq").strip("_.")[:45] or "seq"
    candidate, n = base, 1

    while candidate in used:
        n += 1
        candidate = f"{base}_{n}"

    used.add(candidate)

    return candidate


# --- validation ----------------------------------------------------------------


def validate(package) -> dict:
    """``{"errors": [...], "warnings": [...]}`` for the package's destination."""
    errors, warnings = [], []

    if not package.items.exists():
        errors.append("Add at least one record.")

    if package.destination == D.GENBANK:
        _validate_genbank(package, errors, warnings)
    elif package.destination == D.PDB:
        _validate_pdb(package, errors, warnings)
    elif package.destination == D.ZENODO:
        _validate_zenodo(package, errors, warnings)
    else:
        if not package.taxon_id:
            warnings.append("No taxon chosen: the package will not show up in taxon searches of the repository.")

    return {"errors": errors, "warnings": warnings}


def _validate_genbank(package, errors, warnings):
    sequences = [i for i in _items(package, "sequence") if i.molecule]
    nucleotide = [i for i in sequences if i.molecule.sequence_type in NUCLEOTIDE_TYPES]

    if sequences and not nucleotide:
        errors.append("GenBank takes nucleotide sequences; this package only has proteins.")
    if not nucleotide and not sequences:
        errors.append("GenBank needs at least one sequence record.")
    if not package.taxon_id:
        errors.append("GenBank needs the source organism: choose a taxon.")

    for item in nucleotide:
        m = item.molecule
        seq = (m.sequence or "").upper().replace(" ", "")

        if not NUCLEOTIDE.match(seq or "x"):
            errors.append(f"{m.name}: the sequence has characters that are not nucleotide codes.")
        elif len(seq) < GENBANK_MIN_LENGTH:
            warnings.append(f"{m.name}: {len(seq)} nt is shorter than the {GENBANK_MIN_LENGTH} nt GenBank minimum.")
        if m.sequence_type == "rna":
            warnings.append(f"{m.name}: RNA records need a moltype (mRNA, tRNA, rRNA...) set in the Submission Portal.")
        if m.sequence_type == "primer":
            warnings.append(f"{m.name}: primers are usually not submitted to GenBank.")

    if len(sequences) != len(nucleotide):
        warnings.append("Protein records are left out of the GenBank files; they are annotated on the nucleotide record.")

    warnings.append("Raw reads are not kept in the LIMS; submit them to SRA separately in the same Submission Portal.")


def _validate_pdb(package, errors, warnings):
    structures = [i for i in _items(package, "structure") if i.structure]

    if not structures:
        errors.append("wwPDB needs at least one 3D structure record.")
    if not package.taxon_id:
        warnings.append("Choose a taxon: the deposition asks for the source organism.")
    if not _authors(package):
        warnings.append("Add the authors in the details: the deposition requires them.")

    for item in structures:
        if item.structure.source_format != "mmcif":
            warnings.append(f"{item.label}: wwPDB prefers mmCIF; this file is {item.structure.source_format}.")


def _validate_zenodo(package, errors, warnings):
    if not package.description.strip():
        errors.append("Zenodo needs a description.")
    if not _authors(package):
        warnings.append("No authors given: the record owner will be used as the only creator.")

    license_url = ((package.metadata or {}).get("license") or "").lower()

    if not any(key in license_url for key in CC_LICENSES):
        warnings.append("The license is not one this tool recognizes (CC BY, CC BY-SA, CC BY-NC, CC0): CC BY 4.0 will be proposed.")


# --- files ---------------------------------------------------------------------


def _organism(package) -> str:
    return package.taxon_name or ""


def _json(data) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()


def destination_files(package) -> dict[str, bytes]:
    """Extra files for the package's destination, keyed by relative path."""
    if package.destination == D.GENBANK:
        return _genbank_files(package)
    if package.destination == D.PDB:
        return _pdb_files(package)
    if package.destination == D.ZENODO:
        return _zenodo_files(package)

    return {}


def _genbank_files(package) -> dict[str, bytes]:
    used: set[str] = set()
    fasta, table = [], ["Sequence_ID\tOrganism\tdb_xref"]
    organism = _organism(package)

    for item in _items(package, "sequence"):
        m = item.molecule

        if not m or m.sequence_type not in NUCLEOTIDE_TYPES:
            continue

        seq_id = _seq_id(m.name, used)
        mods = f"[organism={organism}]" if organism else ""

        if m.topology == "circular" or m.sequence_type == "plasmid":
            mods += " [topology=circular]"
        if m.sequence_type in ("dna", "plasmid"):
            mods += " [moltype=genomic]"

        seq = (m.sequence or "").upper().replace(" ", "").replace("U", "T") if m.sequence_type != "rna" else (m.sequence or "").upper().replace(" ", "")

        fasta.append(f">{seq_id} {mods.strip()}\n" + "\n".join(seq[i:i + 70] for i in range(0, len(seq), 70)))
        table.append(f"{seq_id}\t{organism}\t" + (f"taxon:{package.taxon_id}" if package.taxon_id else ""))

    readme = (
        "GenBank / SRA submission (NCBI Submission Portal)\n"
        "==================================================\n"
        "1. Sign in at https://submit.ncbi.nlm.nih.gov/ and start a GenBank submission (nucleotide sequences).\n"
        "2. Upload genbank/sequences.fsa. The organism and topology are already in each definition line.\n"
        "3. If the portal asks for a source table, use genbank/source_modifiers.tsv.\n"
        "4. Fill in the submitter, BioProject and BioSample in the portal.\n"
        "5. For raw reads, open the SRA flow in the same portal and upload them there; they are not stored here.\n"
        "6. After NCBI replies, record the accession on the package page.\n"
    )

    return {
        "genbank/sequences.fsa": ("\n".join(fasta) + "\n").encode(),
        "genbank/source_modifiers.tsv": ("\n".join(table) + "\n").encode(),
        "genbank/README.txt": readme.encode(),
    }


def _pdb_files(package) -> dict[str, bytes]:
    entities, structures = [], []
    seen: set[int] = set()

    for item in _items(package, "structure"):
        s = item.structure

        if not s:
            continue

        structures.append({"label": item.label, "source_format": s.source_format, "molecule": s.molecule.name})

        if s.molecule_id in seen:
            continue

        seen.add(s.molecule_id)

        m = s.molecule
        seq = (m.sequence or "").upper().replace(" ", "")
        organism = f" {_organism(package)} (taxid {package.taxon_id})" if package.taxon_id else ""

        entities.append(f">entity_{len(entities) + 1}|{safe(m.name)}|{m.sequence_type}{organism}\n" + "\n".join(seq[i:i + 70] for i in range(0, len(seq), 70)))

    meta = package.metadata or {}
    deposition = {
        "title": package.title,
        "description": package.description,
        "authors": _authors(package),
        "keywords": [k.strip() for k in re.split(r"[,;]", meta.get("keywords", "")) if k.strip()],
        "source_organism": {"name": _organism(package), "ncbi_taxid": package.taxon_id},
        "funding": meta.get("funding", ""),
        "structures": structures,
    }
    readme = (
        "wwPDB deposition (OneDep)\n"
        "=========================\n"
        "1. Sign in at https://deposit.wwpdb.org/ and start a new deposition (choose the experimental method).\n"
        "2. Upload the coordinate files from the structures/ folder (mmCIF preferred).\n"
        "3. Upload wwpdb/entity_sequences.fasta when the form asks for the sequence of each entity.\n"
        "4. Use wwpdb/deposition_metadata.json to fill in title, authors, keywords and source organism.\n"
        "5. Experimental data (maps, structure factors) are not stored here; add them in the deposition.\n"
        "6. After wwPDB replies, record the PDB id on the package page.\n"
    )

    return {
        "wwpdb/entity_sequences.fasta": ("\n".join(entities) + "\n").encode(),
        "wwpdb/deposition_metadata.json": _json(deposition),
        "wwpdb/README.txt": readme.encode(),
    }


def safe(text: str) -> str:
    return re.sub(r"\s+", "_", (text or "").strip())


def zenodo_metadata(package) -> dict:
    meta = package.metadata or {}
    names = _authors(package) or [package.owner.get_username()]
    license_url = (meta.get("license") or "").lower()
    license_id = next((v for k, v in CC_LICENSES.items() if k in license_url), "cc-by-4.0")
    data = {
        "title": package.title,
        "description": package.description or package.title,
        "upload_type": "dataset",
        "access_right": "open",
        "creators": [{"name": n} for n in names],
        "license": license_id,
        "keywords": [k.strip() for k in re.split(r"[,;]", meta.get("keywords", "")) if k.strip()],
    }

    if package.taxon_id:
        data["subjects"] = [{
            "term": package.taxon_name,
            "identifier": f"https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={package.taxon_id}",
            "scheme": "url",
        }]
    if meta.get("funding"):
        data["notes"] = f"Funding: {meta['funding']}"

    return data


def _zenodo_files(package) -> dict[str, bytes]:
    readme = (
        "Zenodo deposit\n"
        "==============\n"
        "1. Create a new upload at https://zenodo.org/uploads/new (or use the draft created from the package page).\n"
        "2. Upload the files of this folder (everything except this README).\n"
        "3. The metadata is in .zenodo.json; copy it into the form if it was not filled in.\n"
        "4. Review and publish on Zenodo yourself: publishing gives the DOI and cannot be undone.\n"
        "5. Record the DOI on the package page.\n"
    )

    return {".zenodo.json": _json(zenodo_metadata(package)), "zenodo/README.txt": readme.encode()}


# --- Zenodo draft --------------------------------------------------------------


def zenodo_configured() -> bool:
    return bool(getattr(settings, "BIOBANK_ZENODO_TOKEN", ""))


def _zenodo_request(method, url, token, body=None, content_type="application/json", timeout=60):
    request = urllib.request.Request(url, data=body, method=method)

    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", content_type)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()

            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise ValidationError(f"Zenodo refused the request ({exc.code}).")
    except (urllib.error.URLError, OSError, ValueError):
        raise ValidationError("Could not reach Zenodo.")


def upload_zenodo_draft(package, files: dict[str, bytes]) -> str:
    """Create a Zenodo *draft* with the package files. Never publishes. Returns the draft URL."""
    token = getattr(settings, "BIOBANK_ZENODO_TOKEN", "")

    if not token:
        raise ValidationError("Zenodo is not configured on this server.")

    api = getattr(settings, "BIOBANK_ZENODO_API", "https://sandbox.zenodo.org/api").rstrip("/")
    deposition = _zenodo_request("POST", f"{api}/deposit/depositions", token, b"{}")
    bucket = (deposition.get("links") or {}).get("bucket")

    if not deposition.get("id") or not bucket:
        raise ValidationError("Zenodo did not return a draft.")

    for path, data in sorted(files.items()):
        if path.startswith("zenodo/") or path == ".zenodo.json":
            continue

        name = path.replace("/", "__")

        _zenodo_request("PUT", f"{bucket}/{urllib.request.quote(name)}", token, data, "application/octet-stream", timeout=600)

    _zenodo_request("PUT", f"{api}/deposit/depositions/{deposition['id']}", token, json.dumps({"metadata": zenodo_metadata(package)}).encode())

    return (deposition.get("links") or {}).get("html") or f"{api.rsplit('/api', 1)[0]}/deposit/{deposition['id']}"
