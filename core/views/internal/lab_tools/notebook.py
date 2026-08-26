import re
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
    MolecularSecondaryStructure,
    MolecularAlignment,
    MolecularStructure,
    MolecularSequence,
    MolecularFeature,
    NotebookAttachment,
    NotebookBlock,
    NotebookEntry,
    NotebookSampleLink,
    NotebookChemicalLink,
    NotebookMolecularLink,
    NotebookJupyterLink,
    JupyterNotebook,
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
from core.services.molecular_secondary_structure import (
    MolecularSecondaryStructureImportError,
    checksum_secondary_structure_source,
    parse_secondary_structure_source,
    read_secondary_structure_upload,
    validate_dot_bracket,
)

from core.services.molecular_alignment import (
    MolecularAlignmentImportError,
    parse_molecular_alignment,
)

from core.services.molecular_structure import (
    MolecularStructureImportError,
    parse_molecular_structure,
)

from core.services.molecular_file_import import (
    MolecularFileImportError,
    parse_molecular_file,
)

from core.services.jupyter_documents import normalize_notebook


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

    return reverse("chemicals_list")


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



def build_molecular_snapshot(molecule):
    return {
        "id": molecule.id,
        "name": _safe_str(molecule.name),
        "sequence_type": _safe_str(
            molecule.sequence_type
        ),
        "sequence_type_display": (
            molecule.get_sequence_type_display()
        ),
        "topology": _safe_str(molecule.topology),
        "topology_display": (
            molecule.get_topology_display()
        ),
        "length": molecule.length,
        "description": _safe_str(
            molecule.description
        ),
        "checksum_sha256": _safe_str(
            molecule.checksum_sha256
        ),
        "detail_url": reverse(
            "molecular_sequence_detail",
            args=[molecule.id],
        ),
    }


def serialize_notebook_molecular_link(link):
    payload = build_molecular_snapshot(
        link.molecule
    )
    payload.update(
        {
            "status": "success",
            "link_id": link.id,
            "linked_at": (
                link.linked_at.isoformat()
                if link.linked_at
                else ""
            ),
        }
    )
    return payload


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
                file_url = (
                    reverse(
                        "sample_file_download",
                        args=[sample_file.pk],
                    )
                    if sample_file.file
                    else ""
                )
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
        | Q(notebook_links__entry_id__in=visible_entry_ids)
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
        | Q(notebook_links__entry_id__in=visible_entry_ids)
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
    )
    active_entry_id = request.GET.get("entry_id")

    active_entry = None
    linked_sample_links = []
    linked_chemical_links = []
    linked_molecular_links = []
    blocks = []
    attachments = []
    protocol_chemicals = []
    molecular_sequences = []
    experiment_context_counts = {
        "samples": 0,
        "chemicals": 0,
        "molecules": 0,
        "attachments": 0,
        "jupyter": 0,
    }

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
        linked_molecular_links = (
            active_entry.molecular_links
            .select_related(
                "molecule",
                "molecule__owner",
                "molecule__source_entry",
                "molecule__linked_sample",
            )
            .order_by("-linked_at", "-id")
        )
        molecular_sequences = [
            link.molecule
            for link in linked_molecular_links
        ]

        experiment_context_counts = {
            "samples": linked_sample_links.count(),
            "chemicals": linked_chemical_links.count(),
            "molecules": linked_molecular_links.count(),
            "attachments": attachments.count(),
            "jupyter": active_entry.jupyter_links.count(),
        }

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
            "can_edit": bool(
                active_entry
                and (
                    request.user.is_superuser
                    or active_entry.author_id == request.user.id
                )
            ),
            "linked_sample_links": linked_sample_links,
            "linked_chemical_links": linked_chemical_links,
            "linked_molecular_links": linked_molecular_links,
            "linked_samples_json": linked_samples_json,
            "blocks": blocks,
            "attachments": attachments,
            "protocol_chemicals": protocol_chemicals,
            "molecular_sequences": molecular_sequences,
            "experiment_context_counts": experiment_context_counts,
            "notebook_entry_templates": _notebook_entry_templates(),
            "molecular_sequence_types": MolecularSequence.SEQUENCE_TYPE_CHOICES,
            "molecular_topologies": MolecularSequence.TOPOLOGY_CHOICES,
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


def _sectioned_notebook_content(*sections):
    return "".join(
        f"<h2>{section}</h2><p><br></p>"
        for section in sections
    )


def _notebook_entry_templates():
    return {
        "blank": {
            "label": "Blank entry",
            "description": (
                "Start with an empty note and add only "
                "the sections needed."
            ),
            "icon": "bi-file-earmark",
            "title": "Untitled entry",
            "entry_type": "other",
            "content": "",
            "protocol_content": "",
        },
        "experiment": {
            "label": "General experiment",
            "description": (
                "Objective, hypothesis, observations, "
                "results and conclusion."
            ),
            "icon": "bi-flask",
            "title": "New experiment",
            "entry_type": "experiment",
            "content": _sectioned_notebook_content(
                "Objective",
                "Hypothesis",
                "Observations",
                "Results",
                "Conclusion",
            ),
            "protocol_content": (
                "Materials\n\n"
                "Method\n\n"
                "Controls\n\n"
                "Quality criteria\n"
            ),
        },
        "protocol": {
            "label": "Reusable protocol",
            "description": (
                "Materials, procedure, controls, safety "
                "and acceptance criteria."
            ),
            "icon": "bi-list-check",
            "title": "New protocol",
            "entry_type": "protocol",
            "content": _sectioned_notebook_content(
                "Purpose",
                "Scope",
                "Safety and prerequisites",
                "References",
                "Change notes",
            ),
            "protocol_content": (
                "Materials and equipment\n\n"
                "Preparation\n\n"
                "Procedure\n"
                "1. \n"
                "2. \n\n"
                "Controls\n\n"
                "Acceptance criteria\n"
            ),
        },
        "analysis": {
            "label": "Data analysis",
            "description": (
                "Data sources, analytical method, results "
                "and interpretation."
            ),
            "icon": "bi-graph-up",
            "title": "New analysis",
            "entry_type": "analysis",
            "content": _sectioned_notebook_content(
                "Question",
                "Data sources",
                "Analysis plan",
                "Results",
                "Interpretation",
                "Conclusion",
            ),
            "protocol_content": (
                "Software and versions\n\n"
                "Parameters\n\n"
                "Reproducibility notes\n"
            ),
        },
        "sample_characterization": {
            "label": "Sample characterization",
            "description": (
                "Sample context, methods, measurements, "
                "quality control and interpretation."
            ),
            "icon": "bi-droplet",
            "title": "Sample characterization",
            "entry_type": "experiment",
            "content": _sectioned_notebook_content(
                "Characterization objective",
                "Sample context",
                "Measurements",
                "Quality control",
                "Results",
                "Interpretation",
            ),
            "protocol_content": (
                "Sample preparation\n\n"
                "Assay or instrument\n\n"
                "Calibration and controls\n\n"
                "Acceptance criteria\n"
            ),
        },
        "plasmid_construction": {
            "label": "Plasmid construction",
            "description": (
                "Design goal, assembly strategy, screening "
                "and construct validation."
            ),
            "icon": "bi-bezier2",
            "title": "Plasmid construction",
            "entry_type": "experiment",
            "content": _sectioned_notebook_content(
                "Design objective",
                "Vector and insert",
                "Assembly strategy",
                "Screening results",
                "Sequence validation",
                "Final construct",
            ),
            "protocol_content": (
                "DNA inputs\n\n"
                "Assembly method\n\n"
                "Transformation and selection\n\n"
                "Screening plan\n\n"
                "Validation criteria\n"
            ),
        },
        "sequencing_bioinformatics": {
            "label": "Sequencing / bioinformatics",
            "description": (
                "Dataset, pipeline, quality control, "
                "results and biological interpretation."
            ),
            "icon": "bi-code-square",
            "title": "Sequencing / bioinformatics analysis",
            "entry_type": "analysis",
            "content": _sectioned_notebook_content(
                "Analysis objective",
                "Dataset",
                "Pipeline",
                "Quality control",
                "Results",
                "Biological interpretation",
                "Conclusion",
            ),
            "protocol_content": (
                "Input files and checksums\n\n"
                "Software environment\n\n"
                "Pipeline steps\n\n"
                "Parameters\n\n"
                "Output files\n"
            ),
        },
    }


def _notebook_entry_template(template_key):
    templates = _notebook_entry_templates()
    return templates.get(
        template_key,
        templates["experiment"],
    )


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
        content=template["content"],
        protocol_content=template["protocol_content"],
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
def molecular_registry_import_preview_api(request):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST is required.",
            },
            status=405,
        )

    uploaded_file = request.FILES.get("file")

    try:
        imported_record = parse_molecular_file(
            uploaded_file
        )
    except MolecularFileImportError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "ok",
            "record": imported_record,
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
    valid_feature_types = {
        value
        for value, _label
        in MolecularFeature.FEATURE_TYPES
    }
    valid_strands = {
        value
        for value, _label
        in MolecularFeature.STRANDS
    }

    if request.method == "POST":
        uploaded_file = request.FILES.get(
            "molecular_file"
        )
        imported_record = None

        try:
            if uploaded_file is not None:
                imported_record = parse_molecular_file(
                    uploaded_file
                )

            name = str(
                request.POST.get("name")
                or (
                    imported_record.get("name")
                    if imported_record
                    else ""
                )
                or ""
            ).strip()

            if not name:
                raise MolecularSequenceInputError(
                    "Name is required."
                )

            sequence_type = str(
                request.POST.get("sequence_type")
                or (
                    imported_record.get("sequence_type")
                    if imported_record
                    else "dna"
                )
                or "dna"
            ).strip()

            topology = str(
                request.POST.get("topology")
                or (
                    imported_record.get("topology")
                    if imported_record
                    else "linear"
                )
                or "linear"
            ).strip()

            if sequence_type not in valid_sequence_types:
                raise MolecularSequenceInputError(
                    "Invalid sequence type."
                )

            if topology not in valid_topologies:
                raise MolecularSequenceInputError(
                    "Invalid topology."
                )

            # TYPE_AWARE_IMPORT_SELECTION_U1
            if imported_record is not None:
                compatible_types = set(
                    imported_record.get(
                        "compatible_sequence_types"
                    )
                    or []
                )

                if (
                    compatible_types
                    and sequence_type
                    not in compatible_types
                ):
                    detected_label = str(
                        imported_record.get(
                            "detected_content_label"
                        )
                        or "Imported sequence"
                    )

                    raise MolecularSequenceInputError(
                        (
                            f"{detected_label} is not compatible "
                            f"with record type {sequence_type!r}."
                        )
                    )

                if (
                    imported_record.get(
                        "requires_type_confirmation"
                    )
                    and request.POST.get(
                        "type_confirmation"
                    )
                    != "confirmed"
                ):
                    raise MolecularSequenceInputError(
                        (
                            "This nucleotide file does not "
                            "uniquely determine the biological "
                            "record type. Confirm the selected "
                            "record type before creating it."
                        )
                    )

            if sequence_type == "plasmid":
                topology = "circular"

            elif sequence_type in {
                "protein",
                "primer",
                "insert",
            }:
                topology = "linear"

            raw_sequence = (
                request.POST.get("sequence")
                or (
                    imported_record.get("sequence")
                    if imported_record
                    else ""
                )
            )

            sequence = normalize_molecular_sequence(
                raw_sequence,
                sequence_type,
            )

            description = str(
                request.POST.get("description")
                or ""
            ).strip()

            feature_payloads = (
                imported_record.get("features", [])
                if imported_record
                else []
            )

            validated_features = []

            for index, feature_data in enumerate(
                feature_payloads
            ):
                if not isinstance(feature_data, dict):
                    raise MolecularSequenceInputError(
                        "An imported annotation has an invalid structure."
                    )

                feature_name = str(
                    feature_data.get("name")
                    or f"Feature {index + 1}"
                ).strip()[:255]

                feature_type = str(
                    feature_data.get("type")
                    or "custom"
                ).strip()

                if feature_type not in valid_feature_types:
                    feature_type = "custom"

                strand = str(
                    feature_data.get("strand")
                    or "."
                ).strip()

                if strand not in valid_strands:
                    strand = "."

                try:
                    start = int(
                        feature_data.get("start")
                    )
                    end = int(
                        feature_data.get("end")
                    )
                except (
                    TypeError,
                    ValueError,
                ) as exc:
                    raise MolecularSequenceInputError(
                        (
                            f'Annotation “{feature_name}” '
                            "contains invalid coordinates."
                        )
                    ) from exc

                if (
                    start < 1
                    or end < 1
                    or start > len(sequence)
                    or end > len(sequence)
                ):
                    raise MolecularSequenceInputError(
                        (
                            f'Annotation “{feature_name}” '
                            "falls outside the imported sequence."
                        )
                    )

                if (
                    topology != "circular"
                    and start > end
                ):
                    raise MolecularSequenceInputError(
                        (
                            f'Annotation “{feature_name}” '
                            "wraps the origin but the sequence is linear."
                        )
                    )

                color = str(
                    feature_data.get("color")
                    or "#868e96"
                ).strip()

                if not re.fullmatch(
                    r"#[0-9A-Fa-f]{6}",
                    color,
                ):
                    color = "#868e96"

                qualifiers = feature_data.get(
                    "qualifiers",
                    {},
                )

                if not isinstance(qualifiers, dict):
                    qualifiers = {}

                try:
                    order = max(
                        0,
                        int(
                            feature_data.get(
                                "order",
                                index,
                            )
                        ),
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    order = index

                validated_features.append(
                    {
                        "name": feature_name,
                        "feature_type": feature_type,
                        "start": start,
                        "end": end,
                        "strand": strand,
                        "color": color.upper(),
                        "notes": str(
                            feature_data.get("notes")
                            or ""
                        ).strip(),
                        "qualifiers_json": qualifiers,
                        "order": order,
                    }
                )

            with transaction.atomic():
                molecule = MolecularSequence.objects.create(
                    name=name,
                    sequence_type=sequence_type,
                    topology=topology,
                    sequence=sequence,
                    description=description,
                    owner=request.user,
                )

                if validated_features:
                    MolecularFeature.objects.bulk_create(
                        [
                            MolecularFeature(
                                molecule=molecule,
                                **feature_data,
                            )
                            for feature_data
                            in validated_features
                        ]
                    )

        except (
            MolecularFileImportError,
            MolecularSequenceInputError,
        ) as exc:
            messages.error(
                request,
                str(exc),
            )
        else:
            if imported_record:
                messages.success(
                    request,
                    (
                        f'Molecular record “{molecule.name}” '
                        f"was created from "
                        f"{imported_record.get('format_label', 'file')} "
                        f"with {len(validated_features)} annotation(s)."
                    ),
                )
            else:
                messages.success(
                    request,
                    (
                        f'Molecular record “{molecule.name}” '
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

    molecule_count = molecules.count()
    molecules = list(molecules)

    for molecule in molecules:
        molecule.can_delete_from_registry = (
            _can_edit_molecular_sequence(
                request.user,
                molecule,
            )
        )

    return render(
        request,
        "internal/lab_tools/molecular_registry.html",
        {
            "molecules": molecules,
            "molecule_count": molecule_count,
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
def molecular_sequence_restriction_sites_api(
    request,
    sequence_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST is required.",
            },
            status=405,
        )

    molecule = _get_molecular_sequence_for_user(
        sequence_id,
        request.user,
    )

    try:
        data = json.loads(
            request.body.decode("utf-8")
            or "{}"
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "status": "error",
                "message": "Invalid JSON.",
            },
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {
                "status": "error",
                "message": "JSON object required.",
            },
            status=400,
        )

    from core.services.molecular_restriction_sites import (
        MolecularRestrictionSiteError,
        analyze_restriction_sites,
    )

    try:
        if molecule.sequence_type not in {
            "dna",
            "plasmid",
            "primer",
            "insert",
        }:
            raise MolecularRestrictionSiteError(
                (
                    "Restriction-site analysis is available "
                    "for DNA, plasmid, primer and insert "
                    "records only."
                )
            )

        topology = str(
            data.get("topology")
            or molecule.topology
        ).strip().lower()

        if topology not in {
            "linear",
            "circular",
        }:
            raise MolecularRestrictionSiteError(
                "topology must be linear or circular."
            )

        sequence = normalize_molecular_sequence(
            data.get(
                "sequence",
                molecule.sequence,
            ),
            molecule.sequence_type,
        )

        analysis = analyze_restriction_sites(
            sequence,
            topology=topology,
            mode=data.get(
                "mode",
                "unique",
            ),
            catalog=data.get(
                "catalog",
                "common",
            ),
            minimum_site_length=data.get(
                "minimum_site_length",
                6,
            ),
            selected_enzymes=data.get(
                "selected_enzymes",
                [],
            ),
        )

    except (
        MolecularRestrictionSiteError,
        MolecularSequenceInputError,
    ) as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "analysis": analysis,
        }
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
def molecular_sequence_import_api(
    request,
    sequence_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST is required.",
            },
            status=405,
        )

    _get_molecular_sequence_for_user(
        sequence_id,
        request.user,
        require_edit=True,
    )

    uploaded_file = request.FILES.get("file")

    try:
        imported_record = parse_molecular_file(
            uploaded_file
        )
    except MolecularFileImportError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "ok",
            "record": imported_record,
        }
    )



def serialize_molecular_alignment(
    alignment,
):
    return {
        "id": alignment.id,
        "original_filename": (
            alignment.original_filename
        ),
        "source_format": (
            alignment.source_format
        ),
        "source_format_label": (
            alignment.get_source_format_display()
        ),
        "checksum_sha256": (
            alignment.checksum_sha256
        ),
        "sequence_count": (
            alignment.sequence_count
        ),
        "alignment_length": (
            alignment.alignment_length
        ),
        "uploaded_by": (
            alignment.uploaded_by.get_username()
            if alignment.uploaded_by_id
            else ""
        ),
        "created_at": (
            alignment.created_at.isoformat()
            if alignment.created_at
            else ""
        ),
        "updated_at": (
            alignment.updated_at.isoformat()
            if alignment.updated_at
            else ""
        ),
    }


def _alignment_query_match(
    molecule,
    rows,
):
    target = "".join(
        str(
            molecule.sequence
            or ""
        ).split()
    ).upper()

    if not target:
        return None

    for row in rows:
        ungapped = (
            str(
                row.get(
                    "sequence"
                )
                or ""
            )
            .replace(
                "-",
                "",
            )
            .upper()
        )

        if ungapped == target:
            return {
                "index": row.get(
                    "index"
                ),
                "name": row.get(
                    "name"
                ),
            }

    return None


def _read_persisted_molecular_alignment(
    alignment,
    molecule,
):
    try:
        alignment.file.open(
            "rb"
        )

        parsed = parse_molecular_alignment(
            alignment.file
        )

    finally:
        try:
            alignment.file.close()
        except Exception:
            pass

    payload = serialize_molecular_alignment(
        alignment
    )

    payload.update(
        {
            "rows": parsed[
                "rows"
            ],
            "query_match": (
                _alignment_query_match(
                    molecule,
                    parsed[
                        "rows"
                    ],
                )
            ),
        }
    )

    return payload


@login_required
def molecular_sequence_alignments_api(
    request,
    sequence_id,
):
    if request.method not in {
        "GET",
        "POST",
    }:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "GET or POST is required."
                ),
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=(
                request.method
                == "POST"
            ),
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Protein alignments are available "
                    "only for Protein records."
                ),
            },
            status=400,
        )

    if request.method == "GET":
        alignment_id = str(
            request.GET.get(
                "alignment_id"
            )
            or ""
        ).strip()

        if not alignment_id:
            alignments = (
                molecule.alignments
                .select_related(
                    "uploaded_by"
                )
                .all()
            )

            return JsonResponse(
                {
                    "status": "ok",
                    "alignments": [
                        serialize_molecular_alignment(
                            alignment
                        )
                        for alignment
                        in alignments
                    ],
                }
            )

        try:
            alignment_id_int = int(
                alignment_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid alignment id."
                    ),
                },
                status=400,
            )

        alignment = get_object_or_404(
            MolecularAlignment.objects
            .select_related(
                "uploaded_by",
                "molecule",
            ),
            id=alignment_id_int,
            molecule=molecule,
        )

        if (
            request.GET.get(
                "download"
            )
            == "1"
        ):
            try:
                file_handle = (
                    alignment.file.open(
                        "rb"
                    )
                )
            except OSError:
                raise Http404(
                    "Alignment file is unavailable."
                )

            return FileResponse(
                file_handle,
                as_attachment=True,
                filename=(
                    alignment.original_filename
                ),
            )

        try:
            payload = (
                _read_persisted_molecular_alignment(
                    alignment,
                    molecule,
                )
            )

        except (
            MolecularAlignmentImportError,
            OSError,
        ) as exc:
            return JsonResponse(
                {
                    "status": "error",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        return JsonResponse(
            {
                "status": "ok",
                "alignment": payload,
            }
        )

    action = str(
        request.POST.get(
            "action"
        )
        or "upload"
    ).strip().lower()

    if action == "delete":
        alignment_id = str(
            request.POST.get(
                "alignment_id"
            )
            or ""
        ).strip()

        try:
            alignment_id_int = int(
                alignment_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid alignment id."
                    ),
                },
                status=400,
            )

        alignment = get_object_or_404(
            MolecularAlignment,
            id=alignment_id_int,
            molecule=molecule,
        )

        alignment.delete()

        return JsonResponse(
            {
                "status": "success",
                "deleted_id": (
                    alignment_id_int
                ),
            }
        )

    if action != "upload":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Unsupported alignment action."
                ),
            },
            status=400,
        )

    uploaded_file = request.FILES.get(
        "file"
    )

    try:
        parsed = parse_molecular_alignment(
            uploaded_file
        )

    except MolecularAlignmentImportError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(
                    exc
                ),
            },
            status=400,
        )

    duplicate = (
        molecule.alignments
        .filter(
            checksum_sha256=parsed[
                "checksum_sha256"
            ]
        )
        .first()
    )

    if duplicate is not None:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "This exact alignment file "
                    "is already attached to the Protein record."
                ),
                "alignment": (
                    serialize_molecular_alignment(
                        duplicate
                    )
                ),
            },
            status=409,
        )

    alignment = MolecularAlignment(
        molecule=molecule,
        file=uploaded_file,
        original_filename=parsed[
            "original_filename"
        ][
            :255
        ],
        source_format=parsed[
            "source_format"
        ],
        checksum_sha256=parsed[
            "checksum_sha256"
        ],
        sequence_count=parsed[
            "sequence_count"
        ],
        alignment_length=parsed[
            "alignment_length"
        ],
        uploaded_by=request.user,
    )

    try:
        alignment.save()

    except Exception:
        try:
            if (
                alignment.file
                and alignment.file.name
            ):
                alignment.file.delete(
                    save=False
                )
        except Exception:
            pass

        raise

    payload = serialize_molecular_alignment(
        alignment
    )

    payload.update(
        {
            "rows": parsed[
                "rows"
            ],
            "query_match": (
                _alignment_query_match(
                    molecule,
                    parsed[
                        "rows"
                    ],
                )
            ),
        }
    )

    return JsonResponse(
        {
            "status": "success",
            "alignment": payload,
        },
        status=201,
    )




def serialize_molecular_structure(
    structure,
):
    return {
        "id": structure.id,
        "label": structure.label,
        "original_filename": (
            structure.original_filename
        ),
        "source_format": (
            structure.source_format
        ),
        "source_format_label": (
            structure.get_source_format_display()
        ),
        "checksum_sha256": (
            structure.checksum_sha256
        ),
        "uploaded_by": (
            structure.uploaded_by.get_username()
            if structure.uploaded_by_id
            else ""
        ),
        "created_at": (
            structure.created_at.isoformat()
            if structure.created_at
            else ""
        ),
        "updated_at": (
            structure.updated_at.isoformat()
            if structure.updated_at
            else ""
        ),
    }


def _molecular_structure_file_response(
    structure,
    *,
    as_attachment,
):
    try:
        file_handle = (
            structure.file.open(
                "rb"
            )
        )

    except OSError:
        raise Http404(
            "Structure file is unavailable."
        )

    content_type = (
        "chemical/x-pdb"
        if structure.source_format == "pdb"
        else "chemical/x-cif"
    )

    return FileResponse(
        file_handle,
        as_attachment=as_attachment,
        filename=(
            structure.original_filename
        ),
        content_type=content_type,
    )


@login_required
def molecular_sequence_structures_api(
    request,
    sequence_id,
):
    if request.method not in {
        "GET",
        "POST",
    }:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "GET or POST is required."
                ),
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=(
                request.method
                == "POST"
            ),
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Protein structures are currently "
                    "available only for Protein records."
                ),
            },
            status=400,
        )

    # =====================================================
    # GET
    # =====================================================

    if request.method == "GET":
        structure_id = str(
            request.GET.get(
                "structure_id"
            )
            or ""
        ).strip()

        # -------------------------------------------------
        # List
        # -------------------------------------------------

        if not structure_id:
            structures = (
                molecule.structures
                .select_related(
                    "uploaded_by"
                )
                .all()
            )

            return JsonResponse(
                {
                    "status": "ok",
                    "structures": [
                        serialize_molecular_structure(
                            structure
                        )
                        for structure
                        in structures
                    ],
                }
            )

        # -------------------------------------------------
        # Detail/raw/download
        # -------------------------------------------------

        try:
            structure_id_int = int(
                structure_id
            )

        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid structure id."
                    ),
                },
                status=400,
            )

        structure = get_object_or_404(
            MolecularStructure.objects
            .select_related(
                "uploaded_by",
                "molecule",
            ),
            id=structure_id_int,
            molecule=molecule,
        )

        if (
            request.GET.get(
                "download"
            )
            == "1"
        ):
            return (
                _molecular_structure_file_response(
                    structure,
                    as_attachment=True,
                )
            )

        if (
            request.GET.get(
                "raw"
            )
            == "1"
        ):
            return (
                _molecular_structure_file_response(
                    structure,
                    as_attachment=False,
                )
            )

        return JsonResponse(
            {
                "status": "ok",
                "structure": (
                    serialize_molecular_structure(
                        structure
                    )
                ),
            }
        )

    # =====================================================
    # POST
    # =====================================================

    action = str(
        request.POST.get(
            "action"
        )
        or "upload"
    ).strip().lower()

    # -----------------------------------------------------
    # Delete
    # -----------------------------------------------------

    if action == "delete":
        structure_id = str(
            request.POST.get(
                "structure_id"
            )
            or ""
        ).strip()

        try:
            structure_id_int = int(
                structure_id
            )

        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid structure id."
                    ),
                },
                status=400,
            )

        structure = get_object_or_404(
            MolecularStructure,
            id=structure_id_int,
            molecule=molecule,
        )

        structure.delete()

        return JsonResponse(
            {
                "status": "success",
                "deleted_id": (
                    structure_id_int
                ),
            }
        )

    # -----------------------------------------------------
    # Upload
    # -----------------------------------------------------

    if action != "upload":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Unsupported structure action."
                ),
            },
            status=400,
        )

    uploaded_file = request.FILES.get(
        "file"
    )

    try:
        parsed = (
            parse_molecular_structure(
                uploaded_file
            )
        )

    except MolecularStructureImportError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(
                    exc
                ),
            },
            status=400,
        )

    duplicate = (
        molecule.structures
        .filter(
            checksum_sha256=parsed[
                "checksum_sha256"
            ]
        )
        .first()
    )

    if duplicate is not None:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "This exact structure file "
                    "is already attached to the Protein record."
                ),
                "structure": (
                    serialize_molecular_structure(
                        duplicate
                    )
                ),
            },
            status=409,
        )

    label = str(
        request.POST.get(
            "label"
        )
        or ""
    ).strip()[:255]

    structure = MolecularStructure(
        molecule=molecule,
        file=uploaded_file,
        label=label,
        original_filename=parsed[
            "original_filename"
        ][:255],
        source_format=parsed[
            "source_format"
        ],
        checksum_sha256=parsed[
            "checksum_sha256"
        ],
        uploaded_by=request.user,
    )

    try:
        structure.save()

    except Exception:
        try:
            if (
                structure.file
                and structure.file.name
            ):
                structure.file.delete(
                    save=False
                )

        except Exception:
            pass

        raise

    return JsonResponse(
        {
            "status": "success",
            "structure": (
                serialize_molecular_structure(
                    structure
                )
            ),
        },
        status=201,
    )

@login_required
def molecular_sequence_structure_search_api(
    request,
    sequence_id,
):
    """
    Search normalized experimental and computational structure
    providers using the current Molecular Registry Protein
    sequence.

    This endpoint is read-only:

      - no remote structure is persisted;
      - no MolecularStructure row is created;
      - no coordinate file is written to user storage.

    Individual provider degradation is represented inside the
    unified search result rather than promoted to a top-level
    HTTP provider error.
    """

    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "GET is required."
                ),
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=False,
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Structure search is currently "
                    "available only for Protein records."
                ),
            },
            status=400,
        )

    raw_rows = str(
        request.GET.get(
            "rows"
        )
        or "10"
    ).strip()

    try:
        rows = int(
            raw_rows
        )

    except (
        TypeError,
        ValueError,
    ):
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Invalid structure search parameters."
                ),
            },
            status=400,
        )

    from core.services.structure_search import (
        StructureSearchQueryError,
        search_structures_by_sequence,
    )

    try:
        result = (
            search_structures_by_sequence(
                molecule.sequence,
                rows=rows,
            )
        )

    except StructureSearchQueryError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(
                    exc
                ),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "ok",
            "record": {
                "id": molecule.id,
                "name": molecule.name,
                "sequence_length": len(
                    "".join(
                        str(
                            molecule.sequence
                        ).split()
                    )
                ),
            },
            "search": (
                result.to_dict()
            ),
        }
    )


@login_required
def molecular_sequence_structure_preview_api(
    request,
    sequence_id,
):
    """
    Proxy one server-revalidated computational-model mmCIF file.

    The browser supplies only the normalized canonical_key.
    Remote coordinate URLs are never accepted from the client and
    coordinate bytes are never persisted as MolecularStructure data.
    """

    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET is required.",
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=False,
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Predicted structure preview is currently "
                    "available only for Protein records."
                ),
            },
            status=400,
        )

    canonical_key = str(
        request.GET.get(
            "canonical_key"
        )
        or ""
    ).strip()

    if not canonical_key:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "A predicted-model canonical_key "
                    "is required."
                ),
            },
            status=400,
        )

    from core.services.structure_search.preview import (
        StructurePreviewFetchError,
        StructurePreviewQueryError,
        fetch_computational_structure_preview,
    )

    try:
        preview = (
            fetch_computational_structure_preview(
                molecule.sequence,
                canonical_key,
            )
        )

    except StructurePreviewQueryError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(
                    exc
                ),
            },
            status=400,
        )

    except StructurePreviewFetchError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Predicted structure preview is temporarily "
                    f"unavailable: {exc}"
                ),
            },
            status=502,
        )

    from django.http import HttpResponse

    response = HttpResponse(
        preview[
            "content"
        ],
        content_type="chemical/x-cif",
    )

    response[
        "Content-Disposition"
    ] = (
        'inline; filename="'
        + preview[
            "filename"
        ]
        + '"'
    )

    response[
        "X-Biobank-Structure-Preview"
    ] = preview[
        "canonical_key"
    ]

    response[
        "X-Biobank-Structure-Provider"
    ] = preview[
        "provider"
    ]

    response[
        "X-Biobank-Structure-Accession"
    ] = preview[
        "accession"
    ]

    response[
        "Cache-Control"
    ] = (
        "private, max-age=300"
    )

    return response


@login_required
def molecular_sequence_pdb_search_api(
    request,
    sequence_id,
):
    """
    Search experimental RCSB PDB polymer entities using the
    current Molecular Registry Protein sequence.

    This endpoint is intentionally read-only:
      - no remote structure is persisted;
      - no MolecularStructure row is created;
      - no coordinate file is downloaded into user storage.
    """

    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "GET is required."
                ),
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=False,
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "PDB sequence search is currently "
                    "available only for Protein records."
                ),
            },
            status=400,
        )

    raw_identity = str(
        request.GET.get(
            "identity"
        )
        or "0.90"
    ).strip()

    raw_evalue = str(
        request.GET.get(
            "evalue"
        )
        or "0.1"
    ).strip()

    raw_rows = str(
        request.GET.get(
            "rows"
        )
        or "10"
    ).strip()

    try:
        identity = float(
            raw_identity
        )

        evalue = float(
            raw_evalue
        )

        rows = int(
            raw_rows
        )

    except (
        TypeError,
        ValueError,
    ):
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Invalid PDB search parameters."
                ),
            },
            status=400,
        )

    from core.services.rcsb_pdb import (
        RcsbPdbQueryError,
        RcsbPdbSearchError,
        search_pdb_by_sequence,
    )

    try:
        result = (
            search_pdb_by_sequence(
                molecule.sequence,
                identity_cutoff=identity,
                evalue_cutoff=evalue,
                rows=rows,
            )
        )

    except RcsbPdbQueryError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(
                    exc
                ),
            },
            status=400,
        )

    except RcsbPdbSearchError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "RCSB PDB search is temporarily "
                    f"unavailable: {exc}"
                ),
            },
            status=502,
        )

    return JsonResponse(
        {
            "status": "ok",
            "record": {
                "id": molecule.id,
                "name": molecule.name,
                "sequence_length": len(
                    "".join(
                        str(
                            molecule.sequence
                        ).split()
                    )
                ),
            },
            "search": result,
        }
    )


@login_required
def molecular_sequence_pdb_preview_api(
    request,
    sequence_id,
):
    """
    Proxy one validated RCSB mmCIF file for browser preview.

    Coordinate bytes are returned directly to the authenticated
    browser and are not persisted as MolecularStructure data.
    """

    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET is required.",
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=False,
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "PDB preview is currently available "
                    "only for Protein records."
                ),
            },
            status=400,
        )

    pdb_id = str(
        request.GET.get(
            "pdb_id"
        )
        or ""
    ).strip()

    from core.services.rcsb_pdb import (
        RcsbPdbQueryError,
        RcsbPdbSearchError,
        fetch_pdb_mmcif,
    )

    try:
        preview = fetch_pdb_mmcif(
            pdb_id
        )

    except RcsbPdbQueryError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(
                    exc
                ),
            },
            status=400,
        )

    except RcsbPdbSearchError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "RCSB PDB preview is temporarily "
                    f"unavailable: {exc}"
                ),
            },
            status=502,
        )

    from django.http import HttpResponse

    response = HttpResponse(
        preview[
            "content"
        ],
        content_type="chemical/x-cif",
    )

    response[
        "Content-Disposition"
    ] = (
        'inline; filename="'
        + preview[
            "filename"
        ]
        + '"'
    )

    response[
        "X-Biobank-PDB-Preview"
    ] = preview[
        "pdb_id"
    ]

    response[
        "Cache-Control"
    ] = (
        "private, max-age=300"
    )

    return response


@login_required
def molecular_sequence_pdb_mapping_api(
    request,
    sequence_id,
):
    """
    Build a transient Molecular Registry <-> structure residue map.

    The historical endpoint name is retained for compatibility,
    but the implementation is source-agnostic.

    Supported references supplied through ``pdb_id``:

      6B3Q
          Experimental wwPDB / RCSB structure.

      stored:<structure_id>
          PDB or mmCIF already attached to this Protein record.

      computational:<canonical_key>
          Controlled computational Preview, including AlphaFold DB
          and SWISS-MODEL.

    No coordinate bytes or residue mappings are persisted here.
    """

    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "GET is required."
                ),
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=False,
        )
    )

    if molecule.sequence_type != "protein":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Structure residue mapping is "
                    "currently available only for "
                    "Protein records."
                ),
            },
            status=400,
        )

    structure_ref = str(
        request.GET.get(
            "pdb_id"
        )
        or ""
    ).strip()

    entity_id = str(
        request.GET.get(
            "entity_id"
        )
        or ""
    ).strip()

    if not structure_ref:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "A structure reference is required."
                ),
            },
            status=400,
        )

    from core.services.molecular_structure_mapping import (
        MolecularStructureMappingError,
        build_structure_residue_mapping,
    )

    from core.services.rcsb_pdb import (
        RcsbPdbQueryError,
        RcsbPdbSearchError,
        fetch_pdb_mmcif,
    )

    from core.services.structure_search.preview import (
        StructurePreviewFetchError,
        StructurePreviewQueryError,
        fetch_computational_structure_preview,
    )

    source_kind = "pdb"
    compatibility_id = structure_ref
    filename = ""

    source = {
        "kind": "pdb",
        "reference": structure_ref,
        "source_format": "mmcif",
    }

    lower_ref = (
        structure_ref.lower()
    )

    try:
        #
        # Stored/uploaded structure.
        #
        if lower_ref.startswith(
            "stored:"
        ):
            source_kind = "stored"

            raw_id = (
                structure_ref.split(
                    ":",
                    1,
                )[1]
            )

            try:
                structure_id = int(
                    raw_id
                )

            except (
                TypeError,
                ValueError,
            ):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "Invalid stored structure id."
                        ),
                    },
                    status=400,
                )

            structure = get_object_or_404(
                molecule.structures.all(),
                id=structure_id,
            )

            structure.file.open(
                "rb"
            )

            try:
                content = (
                    structure.file.read()
                )

            finally:
                structure.file.close()

            source_format = str(
                structure.source_format
                or ""
            ).strip().lower()

            mapping = (
                build_structure_residue_mapping(
                    molecule.sequence,
                    content,
                    source_format=source_format,
                    entity_id=None,
                )
            )

            filename = (
                structure.original_filename
                or structure.file.name
                or f"structure-{structure.id}"
            )

            source = {
                "kind":
                    "stored",

                "reference":
                    structure_ref,

                "structure_id":
                    structure.id,

                "label": (
                    structure.label
                    or structure.original_filename
                    or f"Structure {structure.id}"
                ),

                "source_format":
                    source_format,
            }

        #
        # Controlled computational Preview.
        #
        elif lower_ref.startswith(
            "computational:"
        ):
            source_kind = "computational"

            #
            # Split the ORIGINAL string, not lower_ref.
            # Canonical model keys can be case-sensitive.
            #
            canonical_key = (
                structure_ref.split(
                    ":",
                    1,
                )[1]
            ).strip()

            if not canonical_key:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "A computational model "
                            "canonical key is required."
                        ),
                    },
                    status=400,
                )

            preview = (
                fetch_computational_structure_preview(
                    molecule.sequence,
                    canonical_key,
                )
            )

            mapping = (
                build_structure_residue_mapping(
                    molecule.sequence,
                    preview[
                        "content"
                    ],
                    source_format="mmcif",
                    entity_id=None,
                )
            )

            filename = (
                preview[
                    "filename"
                ]
            )

            source = {
                "kind":
                    "computational",

                "reference":
                    structure_ref,

                "canonical_key":
                    preview[
                        "canonical_key"
                    ],

                "provider":
                    preview[
                        "provider"
                    ],

                "accession":
                    preview[
                        "accession"
                    ],

                "source_format":
                    "mmcif",
            }

        #
        # Existing experimental PDB Preview.
        #
        else:
            preview = (
                fetch_pdb_mmcif(
                    structure_ref
                )
            )

            mapping = (
                build_structure_residue_mapping(
                    molecule.sequence,
                    preview[
                        "content"
                    ],
                    source_format="mmcif",
                    entity_id=(
                        entity_id
                        or None
                    ),
                )
            )

            compatibility_id = (
                preview[
                    "pdb_id"
                ]
            )

            filename = (
                preview[
                    "filename"
                ]
            )

            source = {
                "kind":
                    "pdb",

                "reference":
                    preview[
                        "pdb_id"
                    ],

                "pdb_id":
                    preview[
                        "pdb_id"
                    ],

                "entity_id":
                    entity_id,

                "source_format":
                    "mmcif",
            }

    except (
        RcsbPdbQueryError,
        StructurePreviewQueryError,
        MolecularStructureMappingError,
    ) as exc:
        return JsonResponse(
            {
                "status":
                    "error",

                "message":
                    str(exc),
            },
            status=400,
        )

    except (
        RcsbPdbSearchError,
        StructurePreviewFetchError,
        OSError,
    ) as exc:
        return JsonResponse(
            {
                "status":
                    "error",

                "message": (
                    "Structure residue mapping is "
                    "temporarily unavailable: "
                    f"{exc}"
                ),
            },
            status=502,
        )

    return JsonResponse(
        {
            "status":
                "ok",

            "record": {
                "id":
                    molecule.id,

                "name":
                    molecule.name,

                "sequence_length":
                    len(
                        "".join(
                            str(
                                molecule.sequence
                            ).split()
                        )
                    ),
            },

            #
            # Compatibility envelope consumed by the existing
            # mapping frontend.
            #
            "pdb": {
                "pdb_id":
                    compatibility_id,

                "filename":
                    filename,
            },

            "source":
                source,

            "mapping_source_kind":
                source_kind,

            "mapping":
                mapping,
        }
    )


def serialize_molecular_secondary_structure(
    secondary_structure,
    *,
    include_source=False,
):
    validated = validate_dot_bracket(
        secondary_structure.structure,
    )

    payload = {
        "id": secondary_structure.id,
        "name": secondary_structure.name,
        "structure": (
            secondary_structure.structure
        ),
        "structure_length": (
            validated[
                "length"
            ]
        ),
        "pair_count": (
            validated[
                "pair_count"
            ]
        ),
        "source_format": (
            secondary_structure.source_format
        ),
        "source_format_label": (
            secondary_structure
            .get_source_format_display()
        ),
        "original_filename": (
            secondary_structure
            .original_filename
        ),
        "checksum_sha256": (
            secondary_structure
            .checksum_sha256
        ),
        "minimum_free_energy": (
            format(
                secondary_structure
                .minimum_free_energy,
                ".4f",
            )
            if (
                secondary_structure
                .minimum_free_energy
                is not None
            )
            else None
        ),
        "source_method": (
            secondary_structure
            .source_method
        ),
        "source_note": (
            secondary_structure
            .source_note
        ),
        "created_by": (
            secondary_structure
            .created_by
            .get_username()
            if (
                secondary_structure
                .created_by_id
            )
            else ""
        ),
        "created_at": (
            secondary_structure
            .created_at
            .isoformat()
            if secondary_structure.created_at
            else ""
        ),
        "updated_at": (
            secondary_structure
            .updated_at
            .isoformat()
            if secondary_structure.updated_at
            else ""
        ),
    }

    if include_source:
        payload[
            "source_text"
        ] = (
            secondary_structure
            .source_text
        )

    return payload


@login_required
def molecular_sequence_secondary_structures_api(
    request,
    sequence_id,
):
    if request.method not in {
        "GET",
        "POST",
    }:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "GET or POST is required."
                ),
            },
            status=405,
        )

    molecule = (
        _get_molecular_sequence_for_user(
            sequence_id,
            request.user,
            require_edit=(
                request.method
                == "POST"
            ),
        )
    )

    if molecule.sequence_type != "rna":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Secondary structures are available "
                    "only for RNA records."
                ),
            },
            status=400,
        )

    if request.method == "GET":
        structure_id = str(
            request.GET.get(
                "structure_id"
            )
            or ""
        ).strip()

        if not structure_id:
            structures = (
                molecule
                .secondary_structures
                .select_related(
                    "created_by"
                )
                .all()
            )

            return JsonResponse(
                {
                    "status": "ok",
                    "secondary_structures": [
                        serialize_molecular_secondary_structure(
                            structure
                        )
                        for structure
                        in structures
                    ],
                }
            )

        try:
            structure_id_int = int(
                structure_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid secondary-structure id."
                    ),
                },
                status=400,
            )

        structure = get_object_or_404(
            MolecularSecondaryStructure
            .objects
            .select_related(
                "created_by",
                "molecule",
            ),
            id=structure_id_int,
            molecule=molecule,
        )

        return JsonResponse(
            {
                "status": "ok",
                "secondary_structure": (
                    serialize_molecular_secondary_structure(
                        structure,
                        include_source=True,
                    )
                ),
            }
        )

    action = str(
        request.POST.get(
            "action"
        )
        or "save"
    ).strip().lower()

    if action == "delete":
        structure_id = str(
            request.POST.get(
                "structure_id"
            )
            or ""
        ).strip()

        try:
            structure_id_int = int(
                structure_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid secondary-structure id."
                    ),
                },
                status=400,
            )

        structure = get_object_or_404(
            MolecularSecondaryStructure,
            id=structure_id_int,
            molecule=molecule,
        )

        structure.delete()

        return JsonResponse(
            {
                "status": "success",
                "deleted_id": structure_id_int,
            }
        )

    if action != "save":
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Unsupported secondary-structure action."
                ),
            },
            status=400,
        )

    uploaded_file = request.FILES.get(
        "file"
    )

    supplied_text = request.POST.get(
        "source_text"
    )

    if (
        uploaded_file is not None
        and supplied_text is not None
        and str(
            supplied_text
        ).strip()
    ):
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Supply either a file or source_text, "
                    "not both."
                ),
            },
            status=400,
        )

    try:
        if uploaded_file is not None:
            uploaded = read_secondary_structure_upload(
                uploaded_file
            )

            source_text = uploaded[
                "source_text"
            ]

            original_filename = uploaded[
                "filename"
            ]

            checksum_sha256 = uploaded[
                "checksum_sha256"
            ]

        else:
            source_text = str(
                supplied_text
                or ""
            )

            if not source_text.strip():
                raise MolecularSecondaryStructureImportError(
                    (
                        "Supply a secondary-structure "
                        "file or source_text."
                    )
                )

            original_filename = ""

            checksum_sha256 = (
                checksum_secondary_structure_source(
                    source_text
                )
            )

        parsed = parse_secondary_structure_source(
            source_text,
            molecule_sequence=molecule.sequence,
            filename=original_filename,
        )

    except MolecularSecondaryStructureImportError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    duplicate = (
        molecule
        .secondary_structures
        .filter(
            checksum_sha256=checksum_sha256
        )
        .first()
    )

    if duplicate is not None:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "This exact secondary-structure "
                    "source is already attached to "
                    "the RNA record."
                ),
                "secondary_structure": (
                    serialize_molecular_secondary_structure(
                        duplicate
                    )
                ),
            },
            status=409,
        )

    requested_name = str(
        request.POST.get(
            "name"
        )
        or ""
    ).strip()

    name = (
        requested_name
        or parsed["name"]
        or "Secondary structure"
    )[:255]

    source_method = str(
        request.POST.get(
            "source_method"
        )
        or ""
    ).strip()[:255]

    source_note = str(
        request.POST.get(
            "source_note"
        )
        or ""
    ).strip()

    structure = MolecularSecondaryStructure(
        molecule=molecule,
        name=name,
        structure=parsed[
            "structure"
        ],
        source_format=parsed[
            "source_format"
        ],
        source_text=source_text,
        original_filename=parsed[
            "original_filename"
        ],
        checksum_sha256=checksum_sha256,
        minimum_free_energy=parsed[
            "minimum_free_energy"
        ],
        source_method=source_method,
        source_note=source_note,
        created_by=request.user,
    )

    structure.save()

    return JsonResponse(
        {
            "status": "success",
            "secondary_structure": (
                serialize_molecular_secondary_structure(
                    structure,
                    include_source=True,
                )
            ),
        },
        status=201,
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

        if sequence_type != molecule.sequence_type:
            raise MolecularSequenceInputError(
                "Sequence classification is fixed after creation. "
                "Create a derived molecular record to change type."
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
def search_molecular_sequences_api(request):
    query = str(
        request.GET.get("q") or ""
    ).strip()
    entry_id = request.GET.get("entry_id")

    if len(query) < 1:
        return JsonResponse({"results": []})

    entry = None
    if entry_id:
        entry = _get_entry_for_user(
            entry_id,
            request.user,
        )

    molecules = (
        _visible_molecular_sequences_for_user(
            request.user
        )
        .filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(checksum_sha256__icontains=query)
        )
    )

    if entry is not None:
        molecules = molecules.exclude(
            notebook_links__entry=entry
        )

    molecules = molecules.order_by(
        "name",
        "id",
    )[:20]

    return JsonResponse(
        {
            "results": [
                build_molecular_snapshot(molecule)
                for molecule in molecules
            ]
        }
    )


@login_required
def notebook_link_molecular_sequence_api(
    request,
    entry_id,
):
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
        molecule = _get_molecular_sequence_for_user(
            data.get("molecule_id"),
            request.user,
        )

        link, created = (
            NotebookMolecularLink.objects
            .get_or_create(
                entry=entry,
                molecule=molecule,
                defaults={
                    "snapshot_json": (
                        build_molecular_snapshot(
                            molecule
                        )
                    ),
                    "linked_by": request.user,
                },
            )
        )

        if not created:
            link.snapshot_json = (
                build_molecular_snapshot(
                    molecule
                )
            )
            if link.linked_by_id is None:
                link.linked_by = request.user
            link.save(
                update_fields=[
                    "snapshot_json",
                    "linked_by",
                ]
            )

        return JsonResponse(
            serialize_notebook_molecular_link(
                link
            )
        )
    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )


@login_required
def notebook_unlink_molecular_sequence_api(
    request,
    entry_id,
    link_id,
):
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

    link = get_object_or_404(
        NotebookMolecularLink.objects
        .select_related("molecule"),
        id=link_id,
        entry=entry,
    )

    molecule_id = link.molecule_id
    link.delete()

    return JsonResponse(
        {
            "status": "success",
            "molecule_id": molecule_id,
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

        NotebookMolecularLink.objects.create(
            entry=entry,
            molecule=molecule,
            snapshot_json=build_molecular_snapshot(
                molecule
            ),
            linked_by=request.user,
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















def _notebook_entry_return_url(entry):
    return (
        f"{reverse('notebook_index')}"
        f"?entry_id={entry.id}"
        f"&tab=items#items-pane"
    )


@login_required
def notebook_link_jupyter(
    request,
    entry_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST required.",
            },
            status=405,
        )

    entry = _get_entry_for_user(
        entry_id,
        request.user,
        require_edit=True,
    )

    notebook_id = request.POST.get(
        "notebook_id"
    )

    notebook = get_object_or_404(
        JupyterNotebook.objects.filter(
            owner_id=entry.author_id,
            is_archived=False,
        ),
        pk=notebook_id,
    )

    NotebookJupyterLink.objects.get_or_create(
        entry=entry,
        notebook=notebook,
        defaults={
            "linked_by": request.user,
        },
    )

    return redirect(
        _notebook_entry_return_url(entry)
    )


@login_required
def notebook_unlink_jupyter(
    request,
    entry_id,
    link_id,
):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST required.",
            },
            status=405,
        )

    entry = _get_entry_for_user(
        entry_id,
        request.user,
        require_edit=True,
    )

    link = get_object_or_404(
        NotebookJupyterLink,
        pk=link_id,
        entry=entry,
    )

    link.delete()

    return redirect(
        _notebook_entry_return_url(entry)
    )
