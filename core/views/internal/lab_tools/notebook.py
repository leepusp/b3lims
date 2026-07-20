from pathlib import Path
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.models.lab_tools.notebook import (
    MolecularSequence,
    MolecularFeature,
    NotebookAttachment,
    NotebookBlock,
    NotebookEntry,
    NotebookKernelDocument,
    NotebookKernelExecution,
    NotebookSampleLink,
    NotebookChemicalLink,
)
from core.models.samples.sample import Sample
from core.models.chemicals.chemical import Chemical
from core.permissions.samples import can_edit_sample, can_view_sample, visible_samples_for_user
from core.permissions.notebook import (
    can_edit_notebook_entry,
    can_view_notebook_entry,
    visible_notebook_entries_for_user,
)

from core.services.molecular_sequences import (
    MolecularSequenceInputError,
    normalize_molecular_sequence,
    validate_molecular_feature,
)
from core.services.jupyter_notebooks import (
    JupyterNotebookError,
    cancel_execution,
    get_or_create_document,
    normalize_notebook,
    persist_document,
    refresh_execution,
    submit_document,
)


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


def _can_edit_molecular_sequence(user, molecule):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if molecule.owner_id == user.id:
        return True

    if (
        molecule.source_entry_id
        and can_edit_notebook_entry(
            user,
            molecule.source_entry,
        )
    ):
        return True

    if (
        molecule.linked_sample_id
        and can_edit_sample(
            user,
            molecule.linked_sample,
        )
    ):
        return True

    return False


def _visible_molecular_sequences_for_user(user):
    molecules = MolecularSequence.objects.select_related(
        "owner",
        "source_entry",
        "linked_sample",
    )

    if user.is_superuser:
        return molecules

    visible_entry_ids = (
        visible_notebook_entries_for_user(user)
        .values_list("id", flat=True)
    )
    visible_sample_ids = (
        visible_samples_for_user(user)
        .values_list("id", flat=True)
    )

    return molecules.filter(
        Q(owner=user)
        | Q(source_entry_id__in=visible_entry_ids)
        | Q(linked_sample_id__in=visible_sample_ids)
    ).distinct()


def _get_molecular_sequence_for_user(
    sequence_id,
    user,
    *,
    require_edit=False,
):
    molecules = MolecularSequence.objects.select_related(
        "owner",
        "source_entry",
        "linked_sample",
    )

    if user.is_superuser:
        molecule = get_object_or_404(
            molecules,
            id=sequence_id,
        )
    else:
        visible_entry_ids = (
            visible_notebook_entries_for_user(user)
            .values_list("id", flat=True)
        )
        visible_sample_ids = (
            visible_samples_for_user(user)
            .values_list("id", flat=True)
        )

        molecule = get_object_or_404(
            molecules.filter(
                Q(owner=user)
                | Q(source_entry_id__in=visible_entry_ids)
                | Q(linked_sample_id__in=visible_sample_ids)
            ).distinct(),
            id=sequence_id,
        )

    if require_edit and not _can_edit_molecular_sequence(
        user,
        molecule,
    ):
        raise PermissionDenied

    return molecule


def _get_entry_for_user(entry_id, user, *, require_edit=False):
    entry = get_object_or_404(
        visible_notebook_entries_for_user(user).prefetch_related(
            "sample_links",
            "chemical_links",
            "blocks",
            "attachments",
        ),
        id=entry_id,
    )

    if require_edit and not can_edit_notebook_entry(user, entry):
        raise PermissionDenied

    return entry


@login_required
def notebook_index(request):
    entries = (
        visible_notebook_entries_for_user(request.user)
        .filter(kernel_document__isnull=True)
    )
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
    sample = get_object_or_404(visible_samples_for_user(request.user), id=sample_id)

    if request.method != "POST":
        raise PermissionDenied("Notebook creation from sample requires POST confirmation.")

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

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)

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

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)

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

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
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

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)

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

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    link = get_object_or_404(NotebookChemicalLink, id=link_id, entry=entry)
    link.delete()

    return JsonResponse({"status": "success"})

@login_required
def notebook_delete_entry_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
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
def molecular_registry_index(request):
    valid_sequence_types = {
        value
        for value, _label
        in MolecularSequence.SEQUENCE_TYPE_CHOICES
    }
    valid_topologies = {
        value
        for value, _label
        in MolecularSequence.TOPOLOGY_CHOICES
    }

    if request.method == "POST":
        try:
            name = str(
                request.POST.get("name") or ""
            ).strip()

            if not name:
                raise MolecularSequenceInputError(
                    "Name is required."
                )

            sequence_type = str(
                request.POST.get(
                    "sequence_type",
                    "dna",
                )
            ).strip()

            topology = str(
                request.POST.get(
                    "topology",
                    "linear",
                )
            ).strip()

            if sequence_type not in valid_sequence_types:
                raise MolecularSequenceInputError(
                    "Invalid sequence type."
                )

            if topology not in valid_topologies:
                raise MolecularSequenceInputError(
                    "Invalid topology."
                )

            sequence = normalize_molecular_sequence(
                request.POST.get("sequence"),
                sequence_type,
            )

            molecule = MolecularSequence.objects.create(
                name=name,
                sequence_type=sequence_type,
                topology=topology,
                sequence=sequence,
                description=str(
                    request.POST.get("description") or ""
                ).strip(),
                owner=request.user,
            )

        except MolecularSequenceInputError as exc:
            messages.error(
                request,
                str(exc),
            )
        else:
            messages.success(
                request,
                (
                    f"Molecular record “{molecule.name}” "
                    "was created."
                ),
            )

            return redirect(
                "molecular_sequence_detail",
                sequence_id=molecule.id,
            )

    molecules = (
        _visible_molecular_sequences_for_user(
            request.user
        )
        .order_by("-updated_at", "-id")
    )

    query = str(
        request.GET.get("q") or ""
    ).strip()
    active_type = str(
        request.GET.get("type") or ""
    ).strip()

    if query:
        molecules = molecules.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(source_entry__title__icontains=query)
            | Q(linked_sample__sample_id__icontains=query)
        ).distinct()

    if active_type in valid_sequence_types:
        molecules = molecules.filter(
            sequence_type=active_type
        )
    else:
        active_type = ""

    return render(
        request,
        "internal/lab_tools/molecular_registry.html",
        {
            "molecules": molecules,
            "molecule_count": molecules.count(),
            "query": query,
            "active_type": active_type,
            "sequence_types": (
                MolecularSequence.SEQUENCE_TYPE_CHOICES
            ),
            "topologies": (
                MolecularSequence.TOPOLOGY_CHOICES
            ),
            "form_data": request.POST,
        },
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
    molecule = _get_molecular_sequence_for_user(
        sequence_id,
        request.user,
    )

    registry_origin = (
        request.GET.get("from") == "registry"
        or not molecule.source_entry_id
    )

    if registry_origin:
        molecular_back_url = reverse(
            "molecular_registry_index"
        )
        molecular_back_label = "Molecular Registry"
        molecular_origin = "registry"
    else:
        molecular_back_url = (
            f"{reverse('notebook_index')}"
            f"?entry_id={molecule.source_entry_id}"
            "&tab=items#items-pane"
        )
        molecular_back_label = "ELN Notebook"
        molecular_origin = "eln"

    return render(
        request,
        "internal/lab_tools/molecular_sequence_detail.html",
        {
            "molecule": molecule,
            "sequence_types": MolecularSequence.SEQUENCE_TYPE_CHOICES,
            "topologies": MolecularSequence.TOPOLOGY_CHOICES,
            "feature_types": MolecularFeature.FEATURE_TYPES,
            "molecular_back_url": molecular_back_url,
            "molecular_back_label": molecular_back_label,
            "molecular_origin": molecular_origin,
            "can_edit_molecule": _can_edit_molecular_sequence(
                request.user,
                molecule,
            ),
        },
    )

@login_required
def molecular_sequence_features_api(request, molecule_id):
    molecule = _get_molecular_sequence_for_user(
        molecule_id,
        request.user,
        require_edit=request.method == "POST",
    )

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
            {
                "status": "error",
                "message": "GET or POST required.",
            },
            status=405,
        )

    try:
        data = json.loads(
            request.body.decode("utf-8") or "{}"
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "status": "error",
                "message": "Invalid JSON.",
            },
            status=400,
        )

    feature_payloads = data.get("features", [])
    if not isinstance(feature_payloads, list):
        return JsonResponse(
            {
                "status": "error",
                "message": "features must be a list.",
            },
            status=400,
        )

    try:
        validated = [
            validate_molecular_feature(item, molecule, order)
            for order, item in enumerate(feature_payloads)
        ]
    except MolecularSequenceInputError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    with transaction.atomic():
        molecule.features.all().delete()

        created = [
            MolecularFeature.objects.create(
                molecule=molecule,
                **feature_data,
            )
            for feature_data in validated
        ]

    return JsonResponse(
        {
            "status": "success",
            "features": [
                serialize_molecular_feature(feature)
                for feature in created
            ],
        }
    )

@login_required
def molecular_sequence_update_api(request, sequence_id):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "Method not allowed.",
            },
            status=405,
        )

    molecule = _get_molecular_sequence_for_user(
        sequence_id,
        request.user,
        require_edit=True,
    )

    try:
        data = json.loads(
            request.body.decode("utf-8") or "{}"
        )

        sequence_type = data.get(
            "sequence_type",
            molecule.sequence_type,
        )
        topology = data.get(
            "topology",
            molecule.topology,
        )

        valid_sequence_types = {
            choice[0]
            for choice in MolecularSequence.SEQUENCE_TYPE_CHOICES
        }
        valid_topologies = {
            choice[0]
            for choice in MolecularSequence.TOPOLOGY_CHOICES
        }

        if sequence_type not in valid_sequence_types:
            raise MolecularSequenceInputError(
                "Invalid sequence type."
            )

        if topology not in valid_topologies:
            raise MolecularSequenceInputError(
                "Invalid topology."
            )

        name = str(data.get("name") or "").strip()
        if not name:
            raise MolecularSequenceInputError(
                "Name is required."
            )

        sequence = normalize_molecular_sequence(
            data.get("sequence"),
            sequence_type,
        )

        feature_payloads = data.get("features")

        if (
            feature_payloads is not None
            and not isinstance(feature_payloads, list)
        ):
            raise MolecularSequenceInputError(
                "features must be a list."
            )

        molecule.name = name
        molecule.sequence_type = sequence_type
        molecule.topology = topology
        molecule.description = str(
            data.get("description") or ""
        ).strip()
        molecule.sequence = sequence

        # Feature validation needs the proposed sequence length
        # and topology before the model is persisted.
        molecule.length = len(sequence)

        validated_features = None

        if feature_payloads is not None:
            validated_features = [
                validate_molecular_feature(
                    feature_payload,
                    molecule,
                    order,
                )
                for order, feature_payload
                in enumerate(feature_payloads)
            ]

        with transaction.atomic():
            molecule.save()

            if validated_features is not None:
                molecule.features.all().delete()

                MolecularFeature.objects.bulk_create(
                    [
                        MolecularFeature(
                            molecule=molecule,
                            **feature_data,
                        )
                        for feature_data in validated_features
                    ]
                )

            saved_features = list(
                molecule.features.all()
            )

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
                "features": [
                    serialize_molecular_feature(feature)
                    for feature in saved_features
                ],
            }
        )

    except (
        json.JSONDecodeError,
        MolecularSequenceInputError,
    ) as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

@login_required
def molecular_sequence_delete_api(request, sequence_id):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "Method not allowed",
            },
            status=405,
        )

    molecule = _get_molecular_sequence_for_user(
        sequence_id,
        request.user,
        require_edit=True,
    )

    registry_origin = (
        request.GET.get("from") == "registry"
        or not molecule.source_entry_id
    )

    if registry_origin:
        redirect_url = reverse(
            "molecular_registry_index"
        )
    else:
        redirect_url = (
            f"{reverse('notebook_index')}"
            f"?entry_id={molecule.source_entry_id}"
            "&tab=items#items-pane"
        )

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
        return JsonResponse(
            {
                "status": "error",
                "message": "Method not allowed.",
            },
            status=405,
        )

    entry = _get_entry_for_user(
        entry_id,
        request.user,
        require_edit=True,
    )

    try:
        data = json.loads(
            request.body.decode("utf-8") or "{}"
        )

        sequence_type = data.get("sequence_type", "dna")
        topology = data.get("topology", "linear")

        valid_sequence_types = {
            choice[0]
            for choice in MolecularSequence.SEQUENCE_TYPE_CHOICES
        }
        valid_topologies = {
            choice[0]
            for choice in MolecularSequence.TOPOLOGY_CHOICES
        }

        if sequence_type not in valid_sequence_types:
            raise MolecularSequenceInputError(
                "Invalid sequence type."
            )

        if topology not in valid_topologies:
            raise MolecularSequenceInputError(
                "Invalid topology."
            )

        name = str(data.get("name") or "").strip()
        if not name:
            raise MolecularSequenceInputError(
                "Name is required."
            )

        sequence = normalize_molecular_sequence(
            data.get("sequence"),
            sequence_type,
        )

        linked_sample = None
        linked_sample_id = data.get("linked_sample_id")

        if linked_sample_id:
            linked_sample = get_object_or_404(
                Sample,
                id=linked_sample_id,
            )

            if (
                not can_view_sample(request.user, linked_sample)
                and not request.user.is_superuser
            ):
                raise PermissionDenied

        molecule = MolecularSequence.objects.create(
            name=name,
            sequence_type=sequence_type,
            topology=topology,
            sequence=sequence,
            description=str(
                data.get("description") or ""
            ).strip(),
            linked_sample=linked_sample,
            source_entry=entry,
            owner=request.user,
        )

        return JsonResponse(
            {
                "status": "success",
                "id": molecule.id,
                "name": molecule.name,
                "sequence_type": molecule.sequence_type,
                "topology": molecule.topology,
                "length": molecule.length,
                "description": molecule.description,
                "source_entry_id": molecule.source_entry_id,
                "detail_url": reverse(
                    "molecular_sequence_detail",
                    args=[molecule.id],
                ),
            }
        )
    except (
        json.JSONDecodeError,
        MolecularSequenceInputError,
    ) as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

@login_required
def notebook_create_block_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)

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

    block = get_object_or_404(NotebookBlock, id=block_id, entry__in=visible_notebook_entries_for_user(request.user))
    if not can_edit_notebook_entry(request.user, block.entry):
        raise PermissionDenied

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

    block = get_object_or_404(NotebookBlock, id=block_id, entry__in=visible_notebook_entries_for_user(request.user))
    if not can_edit_notebook_entry(request.user, block.entry):
        raise PermissionDenied
    block.delete()

    return JsonResponse({"status": "success"})


@login_required
def notebook_attachment_download(request, attachment_id):
    attachment = get_object_or_404(
        NotebookAttachment.objects.select_related("entry", "entry__author"),
        id=attachment_id,
    )

    if not can_view_notebook_entry(request.user, attachment.entry):
        raise PermissionDenied

    if not attachment.file:
        raise Http404("Attachment file not found.")

    try:
        return FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=Path(attachment.file.name).name,
        )
    except FileNotFoundError:
        raise Http404("Attachment file not found.")


@login_required
def notebook_upload_attachment_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)

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
            "url": reverse("notebook_attachment_download", args=[attachment.id]),
            "caption": attachment.caption,
            "attachment_type": attachment.attachment_type,
        }
    )


def _execution_payload(execution):
    return {
        "id": execution.id,
        "job_id": execution.job_id,
        "run_id": execution.run_id,
        "status": execution.status,
        "requested_cell_index": execution.requested_cell_index,
        "cpus": execution.cpus,
        "memory_mb": execution.memory_mb,
        "time_minutes": execution.time_minutes,
        "partition": execution.partition,
        "summary": execution.summary_json or {},
        "submitted_by": (
            execution.submitted_by.get_username()
            if execution.submitted_by
            else ""
        ),
        "submitted_at": execution.submitted_at.isoformat(),
        "started_at": (
            execution.started_at.isoformat()
            if execution.started_at
            else None
        ),
        "finished_at": (
            execution.finished_at.isoformat()
            if execution.finished_at
            else None
        ),
    }


def _document_payload(document, *, can_edit, can_execute):
    latest_execution = document.executions.select_related(
        "submitted_by"
    ).first()
    return {
        "id": document.id,
        "title": document.title,
        "notebook": document.notebook_json,
        "updated_at": document.updated_at.isoformat(),
        "can_edit": can_edit,
        "can_execute": can_execute,
        "latest_execution": (
            _execution_payload(latest_execution)
            if latest_execution
            else None
        ),
    }


def _can_execute_managed_notebook(user, entry):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return bool(
        settings.BIOBANK_JUPYTER_ALLOW_ENTRY_OWNERS
        and entry.author_id == user.id
    )


def _starter_jupyter_notebook(entry, user):
    username = user.get_username() or "ELN user"
    return normalize_notebook(
        {
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "eln-introduction",
                    "metadata": {},
                    "source": (
                        f"# {entry.title}\n\n"
                        "This notebook is linked to the Biobank ELN and runs "
                        "on the DaVinci Slurm cluster."
                    ),
                },
                {
                    "cell_type": "code",
                    "id": "runtime-context",
                    "metadata": {},
                    "source": (
                        "import os\n"
                        "import platform\n\n"
                        f"print('Biobank user: {username}')\n"
                        f"print('ELN entry: {entry.id}')\n"
                        "print('Compute node:', platform.node())\n"
                        "print('Working directory:', os.getcwd())"
                    ),
                    "execution_count": None,
                    "outputs": [],
                },
                {
                    "cell_type": "code",
                    "id": "analysis-workspace",
                    "metadata": {},
                    "source": (
                        "# Add the analysis for this ELN entry here.\n"
                        "values = [1, 2, 3, 4]\n"
                        "sum(values)"
                    ),
                    "execution_count": None,
                    "outputs": [],
                },
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {"name": "python"},
                "biobank": {
                    "entry_id": entry.id,
                    "created_for": username,
                },
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )


@login_required
def notebook_jupyter_launch(request):
    now = timezone.localtime()
    partition_choices = tuple(
        settings.BIOBANK_JUPYTER_PARTITIONS
    )

    defaults = {
        "title": f"Jupyter analysis {now:%Y-%m-%d %H:%M}",
        "partition": settings.BIOBANK_JUPYTER_PARTITION,
        "cpus": settings.BIOBANK_JUPYTER_DEFAULT_CPUS,
        "memory_mb": settings.BIOBANK_JUPYTER_DEFAULT_MEMORY_MB,
        "hours": max(
            1,
            settings.BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES // 60,
        ),
    }

    context = {
        "launch": defaults,
        "launch_partitions": partition_choices,
    }

    if request.method == "GET":
        return render(
            request,
            "internal/lab_tools/notebook_jupyter_launch.html",
            context,
        )

    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET or POST required.",
            },
            status=405,
        )

    launch = {
        "title": str(
            request.POST.get("title") or defaults["title"]
        ).strip(),
        "partition": str(
            request.POST.get("partition")
            or defaults["partition"]
        ).strip(),
        "cpus": request.POST.get(
            "cpus",
            defaults["cpus"],
        ),
        "memory_mb": request.POST.get(
            "memory_mb",
            defaults["memory_mb"],
        ),
        "hours": request.POST.get(
            "hours",
            defaults["hours"],
        ),
    }

    try:
        launch["cpus"] = int(launch["cpus"])
        launch["memory_mb"] = int(launch["memory_mb"])
        launch["hours"] = int(launch["hours"])

        if not launch["title"]:
            raise JupyterNotebookError(
                "Notebook title is required."
            )

        if len(launch["title"]) > 255:
            raise JupyterNotebookError(
                "Notebook title is too long."
            )

        if launch["partition"] not in partition_choices:
            raise JupyterNotebookError(
                "Invalid Slurm partition."
            )

        if launch["cpus"] not in {1, 2, 4, 8}:
            raise JupyterNotebookError(
                "Invalid CPU selection."
            )

        if launch["memory_mb"] not in {
            2048,
            4096,
            8192,
            16384,
            32768,
        }:
            raise JupyterNotebookError(
                "Invalid memory selection."
            )

        if launch["hours"] not in {1, 2, 4}:
            raise JupyterNotebookError(
                "Invalid duration selection."
            )
    except (
        TypeError,
        ValueError,
        JupyterNotebookError,
    ) as exc:
        return render(
            request,
            "internal/lab_tools/notebook_jupyter_launch.html",
            {
                "launch": launch,
                "launch_partitions": partition_choices,
                "launch_error": str(exc),
            },
            status=400,
        )

    entry = NotebookEntry.objects.create(
        title=launch["title"],
        author=request.user,
        entry_type="analysis",
        status="draft",
        visibility="private",
    )

    document = get_or_create_document(entry, request.user)
    document.title = entry.title
    document.notebook_json = _starter_jupyter_notebook(
        entry,
        request.user,
    )
    document.updated_by = request.user
    document.save(
        update_fields=[
            "title",
            "notebook_json",
            "updated_by",
            "updated_at",
        ]
    )
    persist_document(document)

    if _can_execute_managed_notebook(request.user, entry):
        try:
            submit_document(
                document,
                request.user,
                cpus=launch["cpus"],
                memory_mb=launch["memory_mb"],
                time_minutes=launch["hours"] * 60,
                partition=launch["partition"],
                cell_index=None,
            )
            messages.success(
                request,
                (
                    "The starter notebook was submitted "
                    f"to Slurm partition {launch['partition']}."
                ),
            )
        except JupyterNotebookError as exc:
            messages.warning(
                request,
                (
                    "The workspace was created, but "
                    f"Slurm submission failed: {exc}"
                ),
            )

    return redirect(
        "notebook_jupyter_workspace",
        entry_id=entry.id,
    )

@login_required
def notebook_jupyter_workspace(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    return render(
        request,
        "internal/lab_tools/notebook_jupyter_workspace.html",
        {
            "entry": entry,
            "can_edit_jupyter": can_edit_notebook_entry(request.user, entry),
            "can_execute_jupyter": _can_execute_managed_notebook(
                request.user,
                entry,
            ),
        },
    )


@login_required
def notebook_jupyter_document_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    can_edit = can_edit_notebook_entry(request.user, entry)

    if request.method == "GET":
        try:
            document = entry.kernel_document
        except NotebookKernelDocument.DoesNotExist:
            if not can_edit:
                return JsonResponse(
                    {
                        "status": "success",
                        "document": None,
                        "can_edit": False,
                        "can_execute": False,
                    }
                )
            document = get_or_create_document(entry, request.user)

        return JsonResponse(
            {
                "status": "success",
                "document": _document_payload(
                    document,
                    can_edit=can_edit,
                    can_execute=_can_execute_managed_notebook(request.user, entry),
                ),
            }
        )

    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "GET or POST required."},
            status=405,
        )

    if not can_edit:
        raise PermissionDenied

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
        notebook = normalize_notebook(data.get("notebook", {}))
        title = str(data.get("title") or f"{entry.title} analysis").strip()
        if not title:
            raise JupyterNotebookError("Notebook title is required.")
        if len(title) > 255:
            raise JupyterNotebookError("Notebook title is too long.")

        with transaction.atomic():
            document = get_or_create_document(entry, request.user)
            document.title = title
            document.notebook_json = notebook
            document.updated_by = request.user
            document.save(
                update_fields=[
                    "title",
                    "notebook_json",
                    "updated_by",
                    "updated_at",
                ]
            )
            persist_document(document)
    except (json.JSONDecodeError, JupyterNotebookError) as exc:
        return JsonResponse(
            {"status": "error", "message": str(exc)},
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "document": _document_payload(
                document,
                can_edit=True,
                can_execute=_can_execute_managed_notebook(request.user, entry),
            ),
        }
    )


@login_required
def notebook_jupyter_submit_api(request, entry_id):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "POST required."},
            status=405,
        )

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    if not _can_execute_managed_notebook(request.user, entry):
        raise PermissionDenied(
            "You cannot execute this managed notebook."
        )

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
        document = get_or_create_document(entry, request.user)
        resource_execution = document.executions.first()

        cpus = (
            resource_execution.cpus
            if resource_execution
            else settings.BIOBANK_JUPYTER_DEFAULT_CPUS
        )
        memory_mb = (
            resource_execution.memory_mb
            if resource_execution
            else settings.BIOBANK_JUPYTER_DEFAULT_MEMORY_MB
        )
        time_minutes = (
            resource_execution.time_minutes
            if resource_execution
            else settings.BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES
        )
        partition = (
            resource_execution.partition
            if resource_execution
            else settings.BIOBANK_JUPYTER_PARTITION
        )

        active_execution = document.executions.filter(
            status__in=["submitted", "pending", "running"]
        ).first()
        if active_execution:
            active_execution = refresh_execution(active_execution)
        if active_execution and active_execution.status in {
            "submitted",
            "pending",
            "running",
        }:
            raise JupyterNotebookError(
                "This notebook already has an active Slurm execution."
            )

        cell_index = data.get("cell_index")
        if cell_index in {"", None}:
            cell_index = None

        execution = submit_document(
            document,
            request.user,
            cpus=cpus,
            memory_mb=memory_mb,
            time_minutes=time_minutes,
            partition=partition,
            cell_index=cell_index,
        )
    except (json.JSONDecodeError, JupyterNotebookError, TypeError, ValueError) as exc:
        return JsonResponse(
            {"status": "error", "message": str(exc)},
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "execution": _execution_payload(execution),
        }
    )


@login_required
def notebook_jupyter_execution_status_api(request, execution_id):
    if request.method != "GET":
        return JsonResponse(
            {"status": "error", "message": "GET required."},
            status=405,
        )

    execution = get_object_or_404(
        NotebookKernelExecution.objects.select_related(
            "document",
            "document__entry",
            "submitted_by",
        ),
        id=execution_id,
    )
    if not can_view_notebook_entry(request.user, execution.document.entry):
        raise PermissionDenied

    warning = ""
    if execution.status in {"submitted", "pending", "running", "unknown"}:
        try:
            execution = refresh_execution(execution)
        except JupyterNotebookError as exc:
            warning = str(exc)

    return JsonResponse(
        {
            "status": "success",
            "execution": _execution_payload(execution),
            "document": (
                execution.document.notebook_json
                if execution.status == "completed"
                else None
            ),
            "warning": warning,
        }
    )


@login_required
def notebook_jupyter_execution_cancel_api(request, execution_id):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "POST required."},
            status=405,
        )
    execution = get_object_or_404(
        NotebookKernelExecution.objects.select_related(
            "document",
            "document__entry",
        ),
        id=execution_id,
    )
    if not can_edit_notebook_entry(request.user, execution.document.entry):
        raise PermissionDenied
    if not _can_execute_managed_notebook(
        request.user,
        execution.document.entry,
    ):
        raise PermissionDenied

    try:
        cancel_execution(execution)
    except JupyterNotebookError as exc:
        return JsonResponse(
            {"status": "error", "message": str(exc)},
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "execution": _execution_payload(execution),
        }
    )


@login_required
def notebook_jupyter_download(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    document = get_object_or_404(NotebookKernelDocument, entry=entry)
    filename = f"eln-entry-{entry.id}.ipynb"
    response = HttpResponse(
        json.dumps(document.notebook_json, indent=1, ensure_ascii=False),
        content_type="application/x-ipynb+json",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
