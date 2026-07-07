import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    MolecularFeature,
    NotebookAttachment,
    NotebookBlock,
    NotebookEntry,
    NotebookSampleLink,
    NotebookChemicalLink,
)
from core.models.samples.sample import Sample
from core.models.chemicals.chemical import Chemical
from core.permissions.samples import can_view_sample, visible_samples_for_user


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


def _chemical_detail_url(chemical):
    """
    Best-effort URL for Chemical records. Falls back to the Chemical inventory
    page if the project does not expose a dedicated detail route.
    """
    candidate_names = [
        "chemical_detail",
        "chemical_update",
        "chemical_edit",
        "chemical_inventory_detail",
        "chemical_inventory_update",
    ]

    for name in candidate_names:
        try:
            return reverse(name, args=[chemical.id])
        except Exception:
            pass

    return "/biobank/internal/chemicals/"


def build_chemical_snapshot(chemical):
    return {
        "id": chemical.id,
        "name": _safe_str(getattr(chemical, "name", "")),
        "formula": _safe_str(getattr(chemical, "formula", "")),
        "cas_number": _safe_str(getattr(chemical, "cas_number", "")),
        "quantity": _safe_str(getattr(chemical, "quantity", "")),
        "location": _safe_str(getattr(chemical, "location", "")),
        "status": _safe_str(getattr(chemical, "status", "")),
        "expiry_date": chemical.expiry_date.isoformat() if getattr(chemical, "expiry_date", None) else "",
        "msds_link": _safe_str(getattr(chemical, "msds_link", "")),
        "hazard_notes": _safe_str(getattr(chemical, "hazard_notes", "")),
        "detail_url": _chemical_detail_url(chemical),
    }


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
    linked_chemical_links = []
    blocks = []
    attachments = []
    protocol_chemicals = []
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
        linked_chemical_links = (
            active_entry.chemical_links
            .select_related("chemical")
            .order_by("-linked_at")
        )
        blocks = active_entry.blocks.all()
        attachments = active_entry.attachments.all()

        protocol_chemicals = Chemical.objects.all().order_by("name", "id")[:200]
        molecular_sequences = active_entry.molecular_sequences.all().order_by("-updated_at", "-id")

    linked_samples_json = json.dumps(
        [link.snapshot_json for link in linked_sample_links],
        ensure_ascii=False,
    )

    entry_workspace_path = ""
    if active_entry:
        username = request.user.get_username()
        if username:
            entry_workspace_path = f"/home/{username}/biobank_notebooks/entry_{active_entry.id}"

    return render(
        request,
        "internal/lab_tools/notebook.html",
        {
            "entries": entries,
            "active_entry": active_entry,
            "linked_sample_links": linked_sample_links,
            "linked_chemical_links": linked_chemical_links,
            "linked_samples_json": linked_samples_json,
            "blocks": blocks,
            "attachments": attachments,
            "protocol_chemicals": protocol_chemicals,
            "molecular_sequences": molecular_sequences,
            "molecular_sequence_types": MolecularSequence.SEQUENCE_TYPE_CHOICES,
            "molecular_topologies": MolecularSequence.TOPOLOGY_CHOICES,
            "entry_workspace_path": entry_workspace_path,
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
        },
        "experiment": {
            "title": "New experiment",
            "entry_type": "experiment",
        },
        "protocol": {
            "title": "New protocol",
            "entry_type": "protocol",
        },
        "analysis": {
            "title": "New analysis",
            "entry_type": "analysis",
        },
        "sample_characterization": {
            "title": "Sample characterization",
            "entry_type": "experiment",
        },
        "plasmid_construction": {
            "title": "Plasmid construction",
            "entry_type": "experiment",
        },
        "sequencing_bioinformatics": {
            "title": "Sequencing / bioinformatics analysis",
            "entry_type": "analysis",
        },
    }

    return templates.get(template_key, templates["experiment"])


@login_required
def notebook_create(request):
    template_key = request.GET.get("template", "blank")
    template = _notebook_entry_template(template_key)

    new_entry = NotebookEntry.objects.create(
        title=template["title"],
        author=request.user,
        entry_type=template["entry_type"],
        status="draft",
        visibility="private",
        content="",
        protocol_content="",
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

    samples = visible_samples_for_user(request.user).filter(q_object).distinct()[:15]

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
        sample = get_object_or_404(visible_samples_for_user(request.user), id=data.get("sample_id"))
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
def search_chemicals_api(request):
    query = request.GET.get("q", "").strip()

    if len(query) < 1:
        return JsonResponse({"results": []})

    chemicals = Chemical.objects.all().order_by("name", "id")

    chemicals = chemicals.filter(
        Q(name__icontains=query)
        | Q(formula__icontains=query)
        | Q(cas_number__icontains=query)
        | Q(quantity__icontains=query)
        | Q(location__icontains=query)
        | Q(status__icontains=query)
    )[:25]

    results = []
    for chemical in chemicals:
        snapshot = build_chemical_snapshot(chemical)
        results.append(snapshot)

    return JsonResponse({"results": results})


@login_required
def notebook_link_chemical_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required."}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON."}, status=400)

    chemical_id = data.get("chemical_id")
    chemical = get_object_or_404(Chemical, id=chemical_id)

    link, created = NotebookChemicalLink.objects.get_or_create(
        entry=entry,
        chemical=chemical,
        defaults={
            "snapshot_json": build_chemical_snapshot(chemical),
            "linked_by": request.user,
        },
    )

    if not created and not link.snapshot_json:
        link.snapshot_json = build_chemical_snapshot(chemical)
        link.linked_by = request.user
        link.save(update_fields=["snapshot_json", "linked_by"])

    return JsonResponse(
        {
            "status": "success",
            "created": created,
            "link": {
                "id": link.id,
                "chemical": build_chemical_snapshot(chemical),
            },
        }
    )


@login_required
def notebook_unlink_chemical_api(request, entry_id, link_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required."}, status=405)

    entry = _get_entry_for_user(entry_id, request.user)
    link = get_object_or_404(NotebookChemicalLink, id=link_id, entry=entry)
    link.delete()

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


def _get_molecule_for_user(molecule_id, user):
    qs = MolecularSequence.objects.all()

    if user.is_superuser:
        return get_object_or_404(qs, id=molecule_id)

    return get_object_or_404(
        qs.filter(
            Q(owner=user)
            | Q(source_entry__author=user)
            | Q(linked_sample__created_by=user)
        ).distinct(),
        id=molecule_id,
    )


def serialize_molecular_feature(feature):
    return {
        "id": feature.id,
        "name": feature.name,
        "type": feature.feature_type,
        "start": feature.start,
        "end": feature.end,
        "strand": feature.strand,
        "color": feature.color,
        "notes": feature.notes,
        "qualifiers": feature.qualifiers_json or {},
        "order": feature.order,
    }


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
            "features_json": json.dumps(molecule.features_json or [], ensure_ascii=False),
        },
    )


@login_required
def molecular_sequence_features_api(request, molecule_id):
    molecule = _get_molecule_for_user(molecule_id, request.user)

    if request.method == "GET":
        return JsonResponse(
            {
                "status": "success",
                "features": [
                    serialize_molecular_feature(feature)
                    for feature in molecule.features.all()
                ],
            }
        )

    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "GET or POST required."},
            status=405,
        )

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON."}, status=400)

    features = data.get("features", [])
    if not isinstance(features, list):
        return JsonResponse({"status": "error", "message": "features must be a list."}, status=400)

    sequence_length = max(molecule.length or len(molecule.sequence or ""), 1)

    with transaction.atomic():
        molecule.features.all().delete()

        created = []
        for order, item in enumerate(features):
            try:
                start = int(item.get("start") or 1)
                end = int(item.get("end") or start)
            except (TypeError, ValueError):
                start = 1
                end = 1

            start = max(1, min(start, sequence_length))
            end = max(1, min(end, sequence_length))

            if start > end:
                start, end = end, start

            feature = MolecularFeature.objects.create(
                molecule=molecule,
                name=(item.get("name") or "feature")[:255],
                feature_type=item.get("type") or item.get("feature_type") or "custom",
                start=start,
                end=end,
                strand=item.get("strand") if item.get("strand") in ["+", "-", "."] else "+",
                color=item.get("color") or "#868e96",
                notes=item.get("notes") or "",
                qualifiers_json=item.get("qualifiers") or item.get("qualifiers_json") or {},
                order=order,
            )
            created.append(feature)

    return JsonResponse(
        {
            "status": "success",
            "features": [serialize_molecular_feature(feature) for feature in created],
        }
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

        features_raw = data.get("features_json", [])
        if isinstance(features_raw, str):
            features_raw = features_raw.strip() or "[]"
            features_json = json.loads(features_raw)
        elif isinstance(features_raw, list):
            features_json = features_raw
        else:
            features_json = []

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
            features_json=features_json,
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
            "sequence": {"name": "", "sequence_type": "dna", "topology": "linear", "sequence": ""},
            "plasmid": {"name": "", "topology": "circular", "sequence": "", "features": []},
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
