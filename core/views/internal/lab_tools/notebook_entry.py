"""B3 ELN entry page (release 2.0).

A document-centred page modelled on Benchling and eLabFTW: entry list on
the left, open-entry tabs, a full TinyMCE editor, spreadsheets with
formulas, and Notes / Metadata / Steps / Relevant items / Files tabs.
Release 2.1 adds revisions, comments, exclusive edit and file versions.
"""

import json
import re
from datetime import date
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import ResearchGroup
from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_composer import (
    NotebookEntryLink,
    NotebookPin,
    NotebookSpreadsheet,
    NotebookStep,
)
from core.permissions.notebook import (
    can_delete_notebook_entry,
    can_edit_notebook_entry,
    can_manage_notebook_entry_sharing,
    visible_notebook_entries_for_user,
)
from core.services import notebook_collab, notebook_taxonomy, notebook_templates
from core.services.notebook_html import sanitize_notebook_html
from core.views.internal.lab_tools.notebook import _get_entry_for_user, _notebook_entry_templates
from core.views.internal.lab_tools.notebook_composer import composer_state


MAX_SHEETS = 20
MAX_ROWS = 500
MAX_COLS = 60
MAX_CELL = 2000


def _json(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Invalid JSON body.")
    if not isinstance(data, dict):
        raise ValidationError("Invalid JSON body.")
    return data


def _error(exc):
    messages = getattr(exc, "messages", None) or [str(exc)]
    return JsonResponse({"status": "error", "message": " ".join(messages)}, status=400)


def _sheet_payload(sheet):
    return {
        "id": sheet.pk,
        "title": sheet.title,
        "data": sheet.data or [],
        "column_widths": sheet.column_widths or [],
    }


def _relevant_items(entry):
    return {
        "samples": [
            {
                "link_id": link.pk,
                "id": link.sample_id,
                "label": f"{link.sample.sample_id} · {link.sample.organism_name or link.sample.sample_type or ''}".strip(" ·"),
            }
            for link in entry.sample_links.select_related("sample")
        ],
        "chemicals": [
            {
                "link_id": link.pk,
                "id": link.chemical_id,
                "label": link.chemical.name + (f" · CAS {link.chemical.cas_number}" if link.chemical.cas_number else ""),
            }
            for link in entry.chemical_links.select_related("chemical")
        ],
        "molecules": [
            {
                "link_id": link.pk,
                "id": link.molecule_id,
                "label": f"{link.molecule.name} · {link.molecule.get_sequence_type_display()}",
                "url": reverse("molecular_sequence_detail", args=[link.molecule_id]),
            }
            for link in entry.molecular_links.select_related("molecule")
        ],
        "jupyter": [
            {
                "link_id": link.pk,
                "id": link.notebook_id,
                "label": link.notebook.title,
                "url": reverse("jupyter_workspace", args=[link.notebook_id]),
            }
            for link in entry.jupyter_links.select_related("notebook")
        ],
        "jupyter_available": [
            {
                "id": notebook.pk,
                "label": notebook.title,
            }
            for notebook in entry.available_jupyter_notebooks()[:50]
        ],
    }


_UUID_PREFIX = re.compile(r"^[0-9a-f]{32}_")


def _attachment_name(a):
    """The name the user uploaded (storage prepends a random id)."""
    if a.file:
        return _UUID_PREFIX.sub("", Path(a.file.name).name)
    return a.caption or f"File {a.pk}"


def _attachment_payload(a, history=None):
    exists = bool(a.file) and a.file.storage.exists(a.file.name)
    payload = {
        "id": a.pk,
        "name": _attachment_name(a),
        "caption": a.caption,
        "type": a.attachment_type,
        "size": a.file.size if exists else None,
        "checksum": (a.checksum_sha256 or "")[:12],
        "uploaded_by": a.uploaded_by.get_username() if a.uploaded_by else "",
        "uploaded_at": timezone.localtime(a.created_at).strftime("%Y-%m-%d %H:%M"),
        "url": reverse("notebook_attachment_download", args=[a.pk]),
        "version": a.version,
    }
    if history is not None:
        payload["history"] = history
    return payload


def _attachments(entry):
    """Current files of an entry, each with the list of its older versions."""
    rows = list(entry.attachments.select_related("uploaded_by").order_by("-id"))
    by_id = {a.pk: a for a in rows}
    result = []
    for a in rows:
        if not a.is_current:
            continue
        history, seen, cursor = [], {a.pk}, by_id.get(a.previous_id)
        while cursor is not None and cursor.pk not in seen:
            history.append(_attachment_payload(cursor))
            seen.add(cursor.pk)
            cursor = by_id.get(cursor.previous_id)
        result.append(_attachment_payload(a, history))
    return result


@login_required
def notebook_entry(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    can_edit = can_edit_notebook_entry(request.user, entry)

    entry_list = (
        visible_notebook_entries_for_user(request.user)
        .exclude(status="archived")
        .select_related("author")
        .order_by("-updated_at")[:200]
    )

    status_list = list(notebook_taxonomy.statuses_for(entry.research_group))
    current_status = next((x for x in status_list if x.slug == entry.status), None) or (
        notebook_taxonomy.status_lookup().get(entry.status)
    )
    if current_status is not None and current_status not in status_list:
        status_list.append(current_status)  # an entry keeps showing its status after a list change

    page_state = {
        "entry": {
            "id": entry.pk,
            "title": entry.title,
            "custom_id": entry.custom_id,
            "status": entry.status,
            "research_group": entry.research_group_id,
            "category": entry.category_id,
            "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M"),
        },
        "can_edit": can_edit,
        "can_share": can_manage_notebook_entry_sharing(request.user, entry),
        "can_delete": can_delete_notebook_entry(request.user, entry),
        "spreadsheets": [_sheet_payload(s) for s in entry.spreadsheets.all()],
        "relevant": _relevant_items(entry),
        "attachments": _attachments(entry),
        "pinned": NotebookPin.objects.filter(user=request.user, entry=entry).exists(),
        "user": request.user.get_full_name() or request.user.get_username(),
        "urls": {
            "update": reverse("notebook_entry_update_api", args=[entry.pk]),
            "sheets": reverse("notebook_spreadsheets_api", args=[entry.pk]),
            "duplicate": reverse("notebook_duplicate_api", args=[entry.pk]),
            "batch": reverse("notebook_dashboard_batch_api"),
            "dashboard": reverse("notebook_dashboard"),
            "entry": reverse("notebook_entry", args=[0]),
            "relevant": reverse("notebook_relevant_api", args=[entry.pk]),
            "files": reverse("notebook_entry_files_api", args=[entry.pk]),
            "upload": reverse("notebook_upload_attachment_api", args=[entry.pk]),
            "lookup": reverse("notebook_lookup_api", args=[entry.pk]),
            "revisions": reverse("notebook_revisions_api", args=[entry.pk]),
            "comments": reverse("notebook_comments_api", args=[entry.pk]),
            "trace": reverse("notebook_trace_api", args=[entry.pk]),
            "sharing": reverse("notebook_sharing_api", args=[entry.pk]),
            "save_template": reverse("notebook_entry_save_template", args=[entry.pk]),
            "template_options": reverse("notebook_entry_template_options", args=[entry.pk]),
            "lock": reverse("notebook_lock_api", args=[entry.pk]),
            "replace": reverse("notebook_file_replace_api", args=[entry.pk]),
            "file_caption": reverse("notebook_file_caption_api", args=[entry.pk]),
            "file_delete": reverse("notebook_file_delete_api", args=[entry.pk]),
        },
        "comment_count": entry.comments.count(),
    }

    return render(
        request,
        "internal/lab_tools/notebook_entry.html",
        {
            "entry": entry,
            "can_edit": can_edit,
            "can_share": can_manage_notebook_entry_sharing(request.user, entry),
            "can_delete": can_delete_notebook_entry(request.user, entry),
            "content_html": sanitize_notebook_html(entry.content),
            "entry_list": entry_list,
            "entry_types": NotebookEntry.ENTRY_TYPE_CHOICES,
            "statuses": status_list,
            "categories": notebook_taxonomy.categories_for(entry.research_group),
            "my_groups": notebook_taxonomy.user_groups(request.user),
            "current_status": current_status,
            "can_manage_taxonomy": bool(notebook_taxonomy.editable_groups(request.user)),
            "visibilities": NotebookEntry.VISIBILITY_CHOICES,
            "composer_state": composer_state(entry, request.user),
            "page_state": page_state,
            "notebook_entry_templates": {**_notebook_entry_templates(), **notebook_templates.menu_entries(request.user)},
        },
    )


@login_required
def notebook_entry_open_latest(request):
    """Open the most recently modified visible entry, or the dashboard."""
    entry = (
        visible_notebook_entries_for_user(request.user)
        .exclude(status="archived")
        .order_by("-updated_at")
        .first()
    )
    if entry is None:
        return redirect("notebook_dashboard")
    return redirect("notebook_entry", entry_id=entry.pk)


UPDATABLE = {
    "title", "content", "entry_type", "status", "visibility", "project", "experiment_date",
    "research_group", "category",
}


@login_required
@require_POST
def notebook_entry_update_api(request, entry_id):
    """Partial update: only the fields present in the body change."""
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        notebook_collab.check_lock(entry, request.headers.get("X-Lock-Token"))
    except notebook_collab.LockedError as exc:
        return JsonResponse({"status": "locked", "message": str(exc), "holder": exc.holder}, status=423)
    try:
        data = _json(request)
        previous_content = entry.content
        unknown = set(data) - UPDATABLE
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}.")

        fields = []
        if "title" in data:
            title = str(data["title"] or "").strip()[:255]
            entry.title = title or "Untitled entry"
            fields.append("title")
        if "content" in data:
            entry.content = sanitize_notebook_html(data["content"])
            fields.append("content")
        if "research_group" in data:
            group = None
            if data["research_group"] not in (None, ""):
                group = ResearchGroup.objects.filter(pk=data["research_group"]).first()
                if group is None or not notebook_taxonomy.can_use_group(request.user, group):
                    raise ValidationError("Choose one of your research groups.")
            if (group.pk if group else None) != entry.research_group_id:
                entry.research_group = group
                fields.append("research_group")
                # The new group's lists apply: keep the status/category only if they exist there.
                if not notebook_taxonomy.resolve_status_slug(entry, entry.status):
                    entry.status = "draft"
                    fields.append("status")
                if entry.category_id and not notebook_taxonomy.categories_for(group).filter(pk=entry.category_id).exists():
                    entry.category = None
                    fields.append("category")
        if "category" in data:
            category = None
            if data["category"] not in (None, ""):
                category = notebook_taxonomy.categories_for(entry.research_group).filter(pk=data["category"]).first()
                if category is None:
                    raise ValidationError("Invalid category.")
            entry.category = category
            if "category" not in fields:
                fields.append("category")
        if "status" in data and not notebook_taxonomy.resolve_status_slug(entry, data["status"]):
            raise ValidationError("Invalid status.")
        for name, choices in (
            ("entry_type", NotebookEntry.ENTRY_TYPE_CHOICES),
            ("status", None),
            ("visibility", NotebookEntry.VISIBILITY_CHOICES),
        ):
            if name in data:
                if choices is not None and data[name] not in dict(choices):
                    raise ValidationError(f"Invalid {name.replace('_', ' ')}.")
                if (
                    name == "visibility"
                    and data[name] != entry.visibility
                    and not can_delete_notebook_entry(request.user, entry)
                ):
                    # Editors invited through sharing cannot open or close the entry.
                    return JsonResponse(
                        {"status": "error", "message": "Only the author can change the visibility."},
                        status=403,
                    )
                setattr(entry, name, data[name])
                if name not in fields:
                    fields.append(name)
        if "project" in data:
            entry.project = str(data["project"] or "").strip()[:255]
            fields.append("project")
        if "experiment_date" in data:
            value = data["experiment_date"]
            try:
                entry.experiment_date = date.fromisoformat(value) if value else None
            except (TypeError, ValueError):
                raise ValidationError("Experiment date must be YYYY-MM-DD.")
            fields.append("experiment_date")

        if fields:
            entry.save(update_fields=fields + ["updated_at"])
            if "content" in fields:
                notebook_collab.record_revision(entry, previous_content, request.user)
    except ValidationError as exc:
        return _error(exc)

    return JsonResponse(
        {
            "status": "success",
            "updated_at": timezone.localtime(entry.updated_at).strftime("%Y-%m-%d %H:%M"),
        }
    )


def _clean_sheet_data(data):
    if not isinstance(data, list) or len(data) > MAX_ROWS:
        raise ValidationError(f"A spreadsheet holds at most {MAX_ROWS} rows.")
    rows = []
    for row in data:
        if not isinstance(row, list) or len(row) > MAX_COLS:
            raise ValidationError(f"A spreadsheet holds at most {MAX_COLS} columns.")
        clean = []
        for cell in row:
            if cell is None:
                cell = ""
            if not isinstance(cell, (str, int, float, bool)):
                raise ValidationError("Cells must hold text or numbers.")
            cell = str(cell)
            if len(cell) > MAX_CELL:
                raise ValidationError(f"A cell holds at most {MAX_CELL} characters.")
            clean.append(cell)
        rows.append(clean)
    return rows


def _clean_widths(widths):
    if not isinstance(widths, list):
        return []
    clean = []
    for width in widths[:MAX_COLS]:
        try:
            clean.append(max(30, min(600, int(width))))
        except (TypeError, ValueError):
            clean.append(100)
    return clean


@login_required
@require_POST
def notebook_spreadsheets_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        notebook_collab.check_lock(entry, request.headers.get("X-Lock-Token"))
    except notebook_collab.LockedError as exc:
        return JsonResponse({"status": "locked", "message": str(exc), "holder": exc.holder}, status=423)
    try:
        data = _json(request)
        action = data.get("action")
        if action == "add":
            if entry.spreadsheets.count() >= MAX_SHEETS:
                raise ValidationError(f"At most {MAX_SHEETS} spreadsheets per entry.")
            last = entry.spreadsheets.order_by("-position").first()
            sheet = NotebookSpreadsheet.objects.create(
                entry=entry,
                title=str(data.get("title") or "Table").strip()[:120] or "Table",
                data=_clean_sheet_data(data.get("data") or [[""] * 4 for _ in range(6)]),
                position=(last.position + 1) if last else 0,
                created_by=request.user,
            )
        else:
            sheet = get_object_or_404(NotebookSpreadsheet, pk=data.get("sheet_id"), entry=entry)
            if action == "save":
                sheet.data = _clean_sheet_data(data.get("data") or [])
                if "column_widths" in data:
                    sheet.column_widths = _clean_widths(data.get("column_widths"))
                sheet.save()
            elif action == "rename":
                sheet.title = str(data.get("title") or "").strip()[:120] or sheet.title
                sheet.save(update_fields=["title", "updated_at"])
            elif action == "delete":
                sheet.delete()
                return JsonResponse({"status": "success", "deleted": data.get("sheet_id")})
            else:
                raise ValidationError("Unknown spreadsheet action.")
    except ValidationError as exc:
        return _error(exc)

    entry.save(update_fields=["updated_at"])
    return JsonResponse({"status": "success", "sheet": _sheet_payload(sheet)})


@login_required
@require_POST
def notebook_duplicate_api(request, entry_id):
    """Copy an entry the user can see into a new draft they own (eLabFTW duplicate)."""
    source = _get_entry_for_user(entry_id, request.user)

    with transaction.atomic():
        copy = NotebookEntry.objects.create(
            title=f"{source.title} (copy)"[:255],
            content=source.content,
            protocol_content=source.protocol_content,
            entry_type=source.entry_type,
            status="draft",
            visibility="private",
            project=source.project,
            author=request.user,
            metadata=source.metadata or {},
        )
        copy.shared_tags.set(source.shared_tags.all())
        copy.keywords.set(source.keywords.all())
        NotebookStep.objects.bulk_create(
            NotebookStep(entry=copy, body=step.body, group=step.group, position=step.position, deadline=step.deadline)
            for step in source.steps.all()
        )
        NotebookSpreadsheet.objects.bulk_create(
            NotebookSpreadsheet(
                entry=copy, title=sheet.title, data=sheet.data,
                column_widths=sheet.column_widths, position=sheet.position,
                created_by=request.user,
            )
            for sheet in source.spreadsheets.all()
        )
        NotebookEntryLink.objects.create(entry=copy, target=source, created_by=request.user)

    return JsonResponse(
        {"status": "success", "entry_id": copy.pk, "url": reverse("notebook_entry", args=[copy.pk])}
    )


RELEVANT_KINDS = {"samples", "chemicals", "molecules", "jupyter"}


def _relevant_search(kind, user, entry, query):
    from django.db.models import Q

    from core.permissions.chemicals import visible_chemicals_for_user
    from core.permissions.samples import visible_samples_for_user
    from core.views.internal.lab_tools.notebook import _visible_molecular_sequences_for_user

    query = (query or "").strip()
    if kind == "samples":
        qs = visible_samples_for_user(user)
        if query:
            qs = qs.filter(Q(sample_id__icontains=query) | Q(organism_name__icontains=query) | Q(sample_type__icontains=query))
        return [{"id": s.pk, "label": f"{s.sample_id} · {s.organism_name or s.sample_type or ''}".strip(" ·")} for s in qs[:15]]
    if kind == "chemicals":
        qs = visible_chemicals_for_user(user)
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(formula__icontains=query) | Q(cas_number__icontains=query))
        return [{"id": c.pk, "label": c.name + (f" · CAS {c.cas_number}" if c.cas_number else "")} for c in qs.order_by("name")[:15]]
    if kind == "molecules":
        qs = _visible_molecular_sequences_for_user(user)
        if query:
            qs = qs.filter(name__icontains=query)
        return [{"id": m.pk, "label": f"{m.name} · {m.get_sequence_type_display()}"} for m in qs[:15]]
    notebooks = entry.available_jupyter_notebooks()
    if query:
        notebooks = notebooks.filter(title__icontains=query)
    return [{"id": n.pk, "label": n.title} for n in notebooks[:15]]


def _relevant_link(kind, user, entry, object_id):
    from core.models.lab_tools.notebook import (
        JupyterNotebook,
        NotebookChemicalLink,
        NotebookJupyterLink,
        NotebookMolecularLink,
        NotebookSampleLink,
    )
    from core.permissions.chemicals import visible_chemicals_for_user
    from core.permissions.samples import visible_samples_for_user
    from core.views.internal.lab_tools.notebook import (
        _visible_molecular_sequences_for_user,
        build_chemical_snapshot,
        build_molecular_snapshot,
        build_sample_snapshot,
    )

    try:
        object_id = int(object_id)
    except (TypeError, ValueError):
        raise ValidationError("Invalid record.")

    if kind == "samples":
        sample = visible_samples_for_user(user).filter(pk=object_id).first()
        if sample is None:
            raise ValidationError("Sample not found or not visible to you.")
        NotebookSampleLink.objects.get_or_create(
            entry=entry, sample=sample,
            defaults={"snapshot_json": build_sample_snapshot(sample), "linked_by": user},
        )
        entry.mentions.add(sample)
    elif kind == "chemicals":
        chemical = visible_chemicals_for_user(user).filter(pk=object_id).first()
        if chemical is None:
            raise ValidationError("Reagent not found or not visible to you.")
        NotebookChemicalLink.objects.get_or_create(
            entry=entry, chemical=chemical,
            defaults={"snapshot_json": build_chemical_snapshot(chemical), "linked_by": user},
        )
    elif kind == "molecules":
        molecule = _visible_molecular_sequences_for_user(user).filter(pk=object_id).first()
        if molecule is None:
            raise ValidationError("Molecular record not found or not visible to you.")
        NotebookMolecularLink.objects.get_or_create(
            entry=entry, molecule=molecule,
            defaults={"snapshot_json": build_molecular_snapshot(molecule), "linked_by": user},
        )
    else:
        notebook = JupyterNotebook.objects.filter(
            owner_id=entry.author_id, is_archived=False, pk=object_id
        ).first()
        if notebook is None:
            raise ValidationError("Jupyter notebook not found (only the entry owner's notebooks can be linked).")
        NotebookJupyterLink.objects.get_or_create(entry=entry, notebook=notebook, defaults={"linked_by": user})


def _relevant_unlink(kind, entry, link_id):
    manager = {
        "samples": entry.sample_links,
        "chemicals": entry.chemical_links,
        "molecules": entry.molecular_links,
        "jupyter": entry.jupyter_links,
    }[kind]
    manager.filter(pk=link_id).delete()


@login_required
def notebook_relevant_api(request, entry_id):
    """Search (GET) and link/unlink (POST) samples, reagents, molecules and Jupyter notebooks."""
    if request.method == "GET":
        entry = _get_entry_for_user(entry_id, request.user)
        kind = request.GET.get("kind", "")
        if kind not in RELEVANT_KINDS:
            return JsonResponse({"status": "error", "message": "Unknown kind."}, status=400)
        return JsonResponse({"status": "success", "results": _relevant_search(kind, request.user, entry, request.GET.get("q"))})

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed."}, status=405)

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _json(request)
        kind = data.get("kind")
        if kind not in RELEVANT_KINDS:
            raise ValidationError("Unknown kind.")
        if data.get("action") == "link":
            _relevant_link(kind, request.user, entry, data.get("id"))
        elif data.get("action") == "unlink":
            _relevant_unlink(kind, entry, data.get("link_id"))
        else:
            raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return _error(exc)
    return JsonResponse({"status": "success", "relevant": _relevant_items(entry)})


@login_required
def notebook_entry_files_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    return JsonResponse({"status": "success", "attachments": _attachments(entry)})
