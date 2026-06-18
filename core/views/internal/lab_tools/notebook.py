import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    NotebookAttachment,
    NotebookBlock,
    NotebookEntry,
    NotebookSampleLink,
)
from core.models.samples.sample import Sample
from core.permissions.samples import can_view_sample


def _sample_display_name(sample):
    sample_id = getattr(sample, "sample_id", "") or f"sample-{sample.pk}"
    organism = getattr(sample, "organism_name", "") or getattr(sample, "name", "") or ""
    sample_type = getattr(sample, "sample_type", "") or ""

    parts = [sample_id]
    if organism:
        parts.append(organism)
    if sample_type:
        parts.append(f"({sample_type})")

    return " - ".join(parts)


def _safe_str(value):
    if value is None:
        return ""
    return str(value)


def build_sample_snapshot(sample):
    collections = []
    try:
        collections = [str(item) for item in sample.collections.all()]
    except Exception:
        collections = []

    biobank = ""
    try:
        biobank = str(sample.biobank) if sample.biobank else ""
    except Exception:
        biobank = ""

    owner = ""
    try:
        owner = str(sample.owner) if sample.owner else ""
    except Exception:
        owner = ""

    snapshot = {
        "id": sample.id,
        "sample_id": _safe_str(getattr(sample, "sample_id", "")),
        "display_name": _sample_display_name(sample),
        "sample_type": _safe_str(getattr(sample, "sample_type", "")),
        "organism_name": _safe_str(getattr(sample, "organism_name", "")),
        "status": _safe_str(getattr(sample, "status", "")),
        "biobank": biobank,
        "owner": owner,
        "collections": collections,
        "scientific_notes": _safe_str(getattr(sample, "scientific_notes", "")),
        "notes": _safe_str(getattr(sample, "notes", "")),
    }

    for field_name in [
        "strain",
        "genotype",
        "phenotype",
        "source",
        "storage_location",
        "risk_class",
        "biosafety_level",
    ]:
        if hasattr(sample, field_name):
            snapshot[field_name] = _safe_str(getattr(sample, field_name, ""))

    sample_files = []
    try:
        for sample_file in sample.files.all().order_by("-uploaded_at"):
            file_name = _safe_str(getattr(sample_file.file, "name", ""))
            file_url = ""
            try:
                file_url = sample_file.file.url if sample_file.file else ""
            except Exception:
                file_url = ""

            sample_files.append(
                {
                    "id": sample_file.id,
                    "name": file_name,
                    "url": file_url,
                    "category": _safe_str(getattr(sample_file, "category", "")),
                    "description": _safe_str(getattr(sample_file, "description", "")),
                    "mime_type": _safe_str(getattr(sample_file, "mime_type", "")),
                    "file_size": getattr(sample_file, "file_size", None),
                    "uploaded_at": sample_file.uploaded_at.isoformat() if sample_file.uploaded_at else "",
                }
            )
    except Exception:
        sample_files = []

    snapshot["sample_files"] = sample_files

    return snapshot


def _get_molecular_sequence_for_user(sequence_id, user):
    molecule = get_object_or_404(
        MolecularSequence.objects.select_related("source_entry", "linked_sample", "owner"),
        id=sequence_id,
    )

    if user.is_superuser:
        return molecule

    if molecule.owner_id == user.id:
        return molecule

    if molecule.source_entry and molecule.source_entry.author_id == user.id:
        return molecule

    raise PermissionDenied


def _get_entry_for_user(entry_id, user):
    return get_object_or_404(
        NotebookEntry.objects.prefetch_related("sample_links", "blocks", "attachments"),
        id=entry_id,
        author=user,
    )


@login_required
def notebook_index(request):
    entries = NotebookEntry.objects.filter(author=request.user)
    active_entry_id = request.GET.get("entry_id")

    active_entry = None
    linked_sample_links = []
    blocks = []
    attachments = []
    molecular_sequences = []

    if active_entry_id:
        active_entry = _get_entry_for_user(active_entry_id, request.user)
    elif entries.exists():
        active_entry = entries.first()

    if active_entry:
        linked_sample_links = (
            active_entry.sample_links
            .select_related("sample")
            .prefetch_related("sample__files")
            .order_by("-linked_at")
        )
        blocks = active_entry.blocks.all()
        attachments = active_entry.attachments.all()
        molecular_sequences = active_entry.molecular_sequences.all().order_by("-updated_at", "-id")

    linked_samples_json = json.dumps(
        [link.snapshot_json for link in linked_sample_links],
        ensure_ascii=False,
    )

    return render(
        request,
        "internal/lab_tools/notebook.html",
        {
            "entries": entries,
            "active_entry": active_entry,
            "linked_sample_links": linked_sample_links,
            "linked_samples_json": linked_samples_json,
            "blocks": blocks,
            "attachments": attachments,
            "molecular_sequences": molecular_sequences,
            "molecular_sequence_types": MolecularSequence.SEQUENCE_TYPE_CHOICES,
            "molecular_topologies": MolecularSequence.TOPOLOGY_CHOICES,
        },
    )


@login_required
def notebook_create_from_sample(request, sample_id):
    sample = get_object_or_404(Sample, id=sample_id)

    if not can_view_sample(request.user, sample) and not request.user.is_superuser:
        raise PermissionDenied

    snapshot = build_sample_snapshot(sample)

    entry = NotebookEntry.objects.create(
        title=f"ELN - {sample.sample_id}",
        author=request.user,
        entry_type="experiment",
        status="draft",
        visibility="private",
        content=(
            f"<h2>{sample.sample_id}</h2>"
            f"<p><strong>Sample type:</strong> {sample.sample_type or ''}</p>"
            f"<p><strong>Organism:</strong> {sample.organism_name or ''}</p>"
            f"<p><strong>Status:</strong> {sample.status or ''}</p>"
        ),
    )

    NotebookSampleLink.objects.create(
        entry=entry,
        sample=sample,
        snapshot_json=snapshot,
        linked_by=request.user,
    )

    entry.mentions.add(sample)

    return redirect(f"{reverse('notebook_index')}?entry_id={entry.id}")


def _notebook_entry_template(template_key):
    templates = {
        "blank": {
            "title": "Untitled entry",
            "entry_type": "other",
            "content": "",
            "protocol_content": "",
        },
        "experiment": {
            "title": "New experiment",
            "entry_type": "experiment",
            "content": (
                "<h2>Objective</h2>"
                "<p>Describe the scientific question, hypothesis or goal.</p>"
                "<h2>Summary</h2>"
                "<p>Briefly summarize the experiment design and expected outcome.</p>"
                "<h2>Observations</h2>"
                "<p>Record observations, deviations and relevant notes.</p>"
            ),
            "protocol_content": (
                "1. Objective\n"
                "2. Materials and reagents\n"
                "3. Experimental setup\n"
                "4. Procedure\n"
                "5. Quality-control checkpoints\n"
                "6. Expected results\n"
            ),
        },
        "protocol": {
            "title": "New protocol",
            "entry_type": "protocol",
            "content": (
                "<h2>Protocol overview</h2>"
                "<p>Describe what this protocol is used for and when it should be applied.</p>"
                "<h2>Safety notes</h2>"
                "<p>List biosafety, chemical or operational precautions.</p>"
            ),
            "protocol_content": (
                "Purpose\n"
                "- \n\n"
                "Materials\n"
                "- \n\n"
                "Procedure\n"
                "1. \n"
                "2. \n"
                "3. \n\n"
                "Acceptance criteria\n"
                "- \n\n"
                "Troubleshooting\n"
                "- \n"
            ),
        },
        "analysis": {
            "title": "New analysis",
            "entry_type": "analysis",
            "content": (
                "<h2>Analysis goal</h2>"
                "<p>Describe the dataset, question and expected output.</p>"
                "<h2>Inputs</h2>"
                "<p>List files, samples, paths or accession identifiers.</p>"
                "<h2>Results summary</h2>"
                "<p>Summarize findings and interpretation.</p>"
            ),
            "protocol_content": (
                "Input data\n"
                "- \n\n"
                "Software / environment\n"
                "- \n\n"
                "Commands or workflow\n"
                "```bash\n"
                "# commands here\n"
                "```\n\n"
                "Output files\n"
                "- \n"
            ),
        },
        "sample_characterization": {
            "title": "Sample characterization",
            "entry_type": "experiment",
            "content": (
                "<h2>Sample characterization</h2>"
                "<p>Link the sample in Relevant items and describe the characterization goal.</p>"
                "<h2>Phenotype / genotype / QC</h2>"
                "<p>Record observations, measurements and QC results.</p>"
            ),
            "protocol_content": (
                "1. Link sample record\n"
                "2. Confirm sample identity\n"
                "3. Record phenotype/genotype/QC metadata\n"
                "4. Attach raw files or images\n"
                "5. Summarize interpretation\n"
            ),
        },
        "plasmid_construction": {
            "title": "Plasmid construction",
            "entry_type": "experiment",
            "content": (
                "<h2>Plasmid construction</h2>"
                "<p>Describe backbone, insert, assembly strategy and host strain.</p>"
                "<h2>Design rationale</h2>"
                "<p>Record cloning/design decisions.</p>"
                "<h2>Validation</h2>"
                "<p>Record colony PCR, digestion, sequencing or expression validation.</p>"
            ),
            "protocol_content": (
                "Backbone\n"
                "- \n\n"
                "Insert\n"
                "- \n\n"
                "Assembly strategy\n"
                "- Gibson / Golden Gate / restriction-ligation / other\n\n"
                "Transformation host\n"
                "- \n\n"
                "Validation plan\n"
                "1. Colony screening\n"
                "2. Miniprep\n"
                "3. Restriction digest / PCR\n"
                "4. Sequencing confirmation\n"
            ),
        },
        "sequencing_bioinformatics": {
            "title": "Sequencing / bioinformatics analysis",
            "entry_type": "analysis",
            "content": (
                "<h2>Sequencing / bioinformatics analysis</h2>"
                "<p>Describe samples, sequencing data, pipeline and biological objective.</p>"
                "<h2>Dataset</h2>"
                "<p>Record FASTQ/FASTA/VCF/count-table paths and metadata.</p>"
                "<h2>Interpretation</h2>"
                "<p>Summarize main biological and technical findings.</p>"
            ),
            "protocol_content": (
                "Data location\n"
                "- \n\n"
                "Environment\n"
                "- Conda/module/container:\n\n"
                "Workflow\n"
                "1. Input validation\n"
                "2. QC\n"
                "3. Alignment/assembly/annotation/counting\n"
                "4. Statistical analysis\n"
                "5. Figures/tables\n\n"
                "Output directory\n"
                "- \n"
            ),
        },
    }

    return templates.get(template_key, templates["experiment"])


@login_required
def notebook_create(request):
    template_key = request.GET.get("template", "experiment")
    template = _notebook_entry_template(template_key)

    new_entry = NotebookEntry.objects.create(
        title=template["title"],
        author=request.user,
        entry_type=template["entry_type"],
        status="draft",
        visibility="private",
        content=template["content"],
        protocol_content=template["protocol_content"],
    )

    return redirect(f"{reverse('notebook_index')}?entry_id={new_entry.id}")


@login_required
def notebook_save_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)

    try:
        data = json.loads(request.body)
        entry.title = data.get("title", entry.title)
        entry.content = data.get("content", "")
        entry.protocol_content = data.get("protocol_content", entry.protocol_content) or ""

        entry_type = data.get("entry_type")
        status = data.get("status")
        visibility = data.get("visibility")

        if entry_type in {choice[0] for choice in NotebookEntry.ENTRY_TYPE_CHOICES}:
            entry.entry_type = entry_type

        if status in {choice[0] for choice in NotebookEntry.STATUS_CHOICES}:
            entry.status = status

        if visibility in {choice[0] for choice in NotebookEntry.VISIBILITY_CHOICES}:
            entry.visibility = visibility

        entry.project = data.get("project", entry.project) or ""
        entry.experiment_date = data.get("experiment_date") or None

        entry.save()
        return JsonResponse({"status": "success"})
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)


@login_required
def search_samples_api(request):
    query = (request.GET.get("q") or "").strip()

    if len(query) < 2:
        return JsonResponse([], safe=False)

    searchable_fields = [
        field.name
        for field in Sample._meta.fields
        if isinstance(field, (models.CharField, models.TextField))
    ]

    q_object = Q()
    for field_name in searchable_fields:
        q_object |= Q(**{f"{field_name}__icontains": query})

    samples = Sample.objects.filter(q_object).distinct()[:15]

    results = [
        {
            "id": sample.id,
            "value": _sample_display_name(sample),
            "sample_id": getattr(sample, "sample_id", ""),
            "sample_type": getattr(sample, "sample_type", ""),
            "organism_name": getattr(sample, "organism_name", ""),
        }
        for sample in samples
    ]

    return JsonResponse(results, safe=False)


@login_required
def notebook_link_sample_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)

    try:
        data = json.loads(request.body)
        sample = get_object_or_404(Sample, id=data.get("sample_id"))
        snapshot = build_sample_snapshot(sample)

        link, _created = NotebookSampleLink.objects.get_or_create(
            entry=entry,
            sample=sample,
            defaults={
                "snapshot_json": snapshot,
                "linked_by": request.user,
            },
        )

        if not link.snapshot_json:
            link.snapshot_json = snapshot
            link.linked_by = request.user
            link.save()

        entry.mentions.add(sample)

        return JsonResponse(
            {
                "status": "success",
                "sample": snapshot,
                "link_id": link.id,
            }
        )
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)


@login_required
def notebook_unlink_sample_api(request, entry_id, link_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)
    link = get_object_or_404(NotebookSampleLink, id=link_id, entry=entry)

    sample = link.sample
    link.delete()

    if not NotebookSampleLink.objects.filter(entry=entry, sample=sample).exists():
        entry.mentions.remove(sample)

    return JsonResponse({"status": "success"})


@login_required
def notebook_delete_entry_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)
    deleted_title = entry.title

    # Deleting the entry removes database links, blocks and attachment records by cascade.
    # Physical uploaded files are not deleted automatically from storage by Django FileField.
    entry.delete()

    return JsonResponse(
        {
            "status": "success",
            "deleted_title": deleted_title,
            "redirect_url": reverse("notebook_index"),
        }
    )


@login_required
def molecular_sequence_detail(request, sequence_id):
    molecule = _get_molecular_sequence_for_user(sequence_id, request.user)

    return render(
        request,
        "internal/lab_tools/molecular_sequence_detail.html",
        {
            "molecule": molecule,
            "sequence_types": MolecularSequence.SEQUENCE_TYPE_CHOICES,
            "topologies": MolecularSequence.TOPOLOGY_CHOICES,
        },
    )


@login_required
def molecular_sequence_update_api(request, sequence_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    molecule = _get_molecular_sequence_for_user(sequence_id, request.user)

    try:
        data = json.loads(request.body)

        sequence_type = data.get("sequence_type", molecule.sequence_type)
        topology = data.get("topology", molecule.topology)

        valid_sequence_types = {choice[0] for choice in MolecularSequence.SEQUENCE_TYPE_CHOICES}
        valid_topologies = {choice[0] for choice in MolecularSequence.TOPOLOGY_CHOICES}

        if sequence_type not in valid_sequence_types:
            return JsonResponse({"status": "error", "message": "Invalid sequence type"}, status=400)

        if topology not in valid_topologies:
            return JsonResponse({"status": "error", "message": "Invalid topology"}, status=400)

        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"status": "error", "message": "Name is required"}, status=400)

        molecule.name = name
        molecule.sequence_type = sequence_type
        molecule.topology = topology
        molecule.description = data.get("description", "") or ""
        molecule.sequence = data.get("sequence", "") or ""

        features_raw = data.get("features_json", "[]")
        if isinstance(features_raw, str):
            features_raw = features_raw.strip() or "[]"
            molecule.features_json = json.loads(features_raw)
        elif isinstance(features_raw, list):
            molecule.features_json = features_raw
        else:
            return JsonResponse({"status": "error", "message": "Features must be a JSON list"}, status=400)

        molecule.save()

        return JsonResponse(
            {
                "status": "success",
                "id": molecule.id,
                "name": molecule.name,
                "sequence_type": molecule.sequence_type,
                "topology": molecule.topology,
                "length": molecule.length,
                "gc_content": molecule.gc_content,
                "checksum_sha256": molecule.checksum_sha256,
            }
        )
    except json.JSONDecodeError as exc:
        return JsonResponse({"status": "error", "message": f"Invalid JSON: {exc}"}, status=400)
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)


@login_required
def molecular_sequence_delete_api(request, sequence_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    molecule = _get_molecular_sequence_for_user(sequence_id, request.user)
    redirect_url = reverse("notebook_index")

    if molecule.source_entry_id:
        redirect_url = f"{reverse('notebook_index')}?entry_id={molecule.source_entry_id}"

    molecule.delete()

    return JsonResponse(
        {
            "status": "success",
            "redirect_url": redirect_url,
        }
    )


@login_required
def notebook_create_molecular_sequence_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)

    try:
        data = json.loads(request.body)

        sequence_type = data.get("sequence_type", "dna")
        topology = data.get("topology", "linear")

        valid_sequence_types = {choice[0] for choice in MolecularSequence.SEQUENCE_TYPE_CHOICES}
        valid_topologies = {choice[0] for choice in MolecularSequence.TOPOLOGY_CHOICES}

        if sequence_type not in valid_sequence_types:
            sequence_type = "dna"

        if topology not in valid_topologies:
            topology = "linear"

        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"status": "error", "message": "Name is required"}, status=400)

        sequence = (data.get("sequence") or "").strip()
        description = (data.get("description") or "").strip()

        linked_sample = None
        linked_sample_id = data.get("linked_sample_id")
        if linked_sample_id:
            linked_sample = get_object_or_404(Sample, id=linked_sample_id)
            if not can_view_sample(request.user, linked_sample) and not request.user.is_superuser:
                raise PermissionDenied

        molecular_sequence = MolecularSequence.objects.create(
            name=name,
            sequence_type=sequence_type,
            topology=topology,
            sequence=sequence,
            description=description,
            linked_sample=linked_sample,
            source_entry=entry,
            owner=request.user,
        )

        return JsonResponse(
            {
                "status": "success",
                "id": molecular_sequence.id,
                "name": molecular_sequence.name,
                "sequence_type": molecular_sequence.sequence_type,
                "topology": molecular_sequence.topology,
                "length": molecular_sequence.length,
            }
        )
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)


@login_required
def notebook_create_block_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)

    try:
        data = json.loads(request.body)
        block_type = data.get("block_type", "text")

        valid_types = {choice[0] for choice in NotebookBlock.BLOCK_TYPE_CHOICES}
        if block_type not in valid_types:
            return JsonResponse({"status": "error", "message": "Invalid block type"}, status=400)

        default_content = {
            "text": {"html": ""},
            "image": {"url": "", "caption": ""},
            "table": {"raw": "", "content": []},
            "code": {
                "code": "# table_1, table_2, ... are available as pandas DataFrames when table blocks exist.\n# Example:\n# fig = px.bar(table_1, x='condition', y='value')\n",
                "last_result": "",
            },
            "sequence": {"name": "", "sequence_type": "dna", "topology": "linear", "sequence": ""},
            "plasmid": {"name": "", "topology": "circular", "sequence": "", "features": []},
            "slurm_job": {
                "job_name": "",
                "partition": "",
                "cpus": 1,
                "memory": "",
                "time_limit": "",
                "command": "",
                "status": "draft",
            },
            "attachment": {},
        }

        next_order = (entry.blocks.aggregate(models.Max("order")).get("order__max") or 0) + 10

        block = NotebookBlock.objects.create(
            entry=entry,
            block_type=block_type,
            title=data.get("title", block_type.replace("_", " ").title()),
            order=next_order,
            content_data=data.get("content_data") or default_content.get(block_type, {}),
            created_by=request.user,
        )

        return JsonResponse({"status": "success", "block_id": block.id})
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)


@login_required
def notebook_update_block_api(request, block_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    block = get_object_or_404(NotebookBlock, id=block_id, entry__author=request.user)

    try:
        data = json.loads(request.body)
        block.title = data.get("title", block.title)
        block.content_data = data.get("content_data", block.content_data)
        block.order = data.get("order", block.order)
        block.save()
        return JsonResponse({"status": "success"})
    except Exception as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)


@login_required
def notebook_delete_block_api(request, block_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    block = get_object_or_404(NotebookBlock, id=block_id, entry__author=request.user)
    block.delete()

    return JsonResponse({"status": "success"})


@login_required
def notebook_upload_attachment_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"status": "error", "message": "No file uploaded"}, status=400)

    block = None
    block_id = request.POST.get("block_id")
    if block_id:
        block = get_object_or_404(NotebookBlock, id=block_id, entry=entry)

    content_type = uploaded_file.content_type or ""
    attachment_type = "image" if content_type.startswith("image/") else "other"

    attachment = NotebookAttachment.objects.create(
        entry=entry,
        block=block,
        file=uploaded_file,
        attachment_type=attachment_type,
        caption=request.POST.get("caption", ""),
        uploaded_by=request.user,
    )

    return JsonResponse(
        {
            "status": "success",
            "attachment_id": attachment.id,
            "url": attachment.file.url,
            "caption": attachment.caption,
            "attachment_type": attachment.attachment_type,
        }
    )
