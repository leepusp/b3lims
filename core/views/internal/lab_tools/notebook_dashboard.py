"""ELN dashboard: the list of Notebook entries (eLabFTW "Experiments" page)."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models.lab_tools.notebook import NotebookEntry
from core.models import Tag
from core.models.lab_tools.notebook_composer import NotebookPin, NotebookStep
from core.services.metadata_vocabularies import get_or_create_active_tag
from core.models.lab_tools.notebook_collab import NotebookEditLock
from core.permissions.notebook import (
    can_delete_notebook_entry,
    can_edit_notebook_entry,
    shared_with_user,
    trashed_notebook_entries_for_user,
    visible_notebook_entries_for_user,
)
from core.models import NotebookStatus
from core.services import notebook_taxonomy, notebook_templates
from core.services.notebook_composer import TAG_RE
from core.services.notebook_search import HELP_ROWS, SearchSyntaxError, build_query


SORTS = {
    "modified": ("-updated_at", "Last modified"),
    "created": ("-created_at", "Newest"),
    "date": ("-experiment_date", "Experiment date"),
    "title": ("title", "Title"),
    "rating": ("-rating", "Rating"),
}

PAGE_SIZE = 25
BATCH_LIMIT = 200


def _filtered_entries(request):
    user = request.user
    params = request.GET
    filters = {
        "q": (params.get("q") or "").strip(),
        "type": params.get("type") or "",
        "status": params.get("status") or "",
        "owner": params.get("owner") or "",
        "tag": (params.get("tag") or "").strip().lower(),
        "state": params.get("state") or "active",
        "sort": params.get("sort") if params.get("sort") in SORTS else "modified",
    }

    if filters["state"] == "trash":
        qs = trashed_notebook_entries_for_user(user)
    else:
        qs = visible_notebook_entries_for_user(user)
        if filters["state"] == "archived":
            qs = qs.filter(status="archived")
        elif filters["state"] != "all":
            filters["state"] = "active"
            qs = qs.exclude(status="archived")

    filters["q_error"] = ""
    filters["q_structured"] = False
    if filters["q"]:
        try:
            condition, filters["q_structured"] = build_query(filters["q"], user)
        except SearchSyntaxError as exc:
            filters["q_error"] = str(exc)
            qs = qs.none()
        else:
            qs = qs.filter(condition)

    if filters["type"] in dict(NotebookEntry.ENTRY_TYPE_CHOICES):
        qs = qs.filter(entry_type=filters["type"])
    else:
        filters["type"] = ""

    if NotebookStatus.objects.filter(slug=filters["status"]).exists():
        qs = qs.filter(status=filters["status"])
    else:
        filters["status"] = ""

    if filters["owner"] == "me":
        qs = qs.filter(author=user)
    elif filters["owner"] == "others":
        qs = qs.exclude(author=user)
    elif filters["owner"] == "shared":
        # Entries other people shared with me (or my groups) through an explicit grant.
        qs = qs.filter(pk__in=shared_with_user(user).values("pk"))
    else:
        filters["owner"] = ""

    if filters["tag"]:
        qs = qs.filter(shared_tags__name__iexact=filters["tag"])

    qs = (
        qs.distinct()
        .select_related("author")
        .prefetch_related("shared_tags")
        .annotate(
            step_total=Count("steps", distinct=True),
            step_done=Count("steps", filter=Q(steps__finished=True), distinct=True),
            is_pinned=Exists(NotebookPin.objects.filter(user=user, entry=OuterRef("pk"))),
        )
        .order_by(SORTS[filters["sort"]][0], "-id")
    )
    return qs, filters


@login_required
def notebook_dashboard(request):
    user = request.user
    entries, filters = _filtered_entries(request)
    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("page"))

    visible = visible_notebook_entries_for_user(user)
    mine = visible.filter(author=user)
    now = timezone.now()

    open_steps = (
        NotebookStep.objects.filter(entry__in=mine, finished=False, deadline__isnull=False)
        .select_related("entry")
        .order_by("deadline")
    )

    pinned = (
        visible.filter(pins__user=user)
        .annotate(
            step_total=Count("steps", distinct=True),
            step_done=Count("steps", filter=Q(steps__finished=True), distinct=True),
        )
        .order_by("-updated_at")[:8]
    )

    tag_cloud = (
        Tag.objects.filter(notebook_entries__in=visible)
        .annotate(n=Count("notebook_entries", distinct=True))
        .order_by("-n", "name")[:24]
    )

    query = request.GET.copy()
    query.pop("page", None)

    from core.views.internal.lab_tools.notebook import _notebook_entry_templates

    return render(
        request,
        "internal/lab_tools/notebook_dashboard.html",
        {
            "page": page,
            "filters": filters,
            "query_string": query.urlencode(),
            "sorts": [(key, label) for key, (_, label) in SORTS.items()],
            "entry_types": NotebookEntry.ENTRY_TYPE_CHOICES,
            "statuses": _status_options(),
            "can_manage_taxonomy": bool(notebook_taxonomy.editable_groups(user)),
            "pinned": pinned,
            "tag_cloud": tag_cloud,
            "stats": {
                "visible": visible.exclude(status="archived").count(),
                "mine": mine.exclude(status="archived").count(),
                "in_progress": mine.filter(status__in=_slugs(NotebookStatus.Kind.ACTIVE)).count(),
                "to_review": visible.filter(status__in=_slugs(NotebookStatus.Kind.DONE)).count(),
                "overdue": open_steps.filter(deadline__lt=now).count(),
            },
            "search_help": HELP_ROWS,
            "shared_count": shared_with_user(user).exclude(status="archived").count(),
            "trash_count": trashed_notebook_entries_for_user(user).count(),
            "due_steps": open_steps[:6],
            "now": now,
            "recent": mine.order_by("-updated_at")[:5],
            "notebook_entry_templates": {**_notebook_entry_templates(), **notebook_templates.menu_entries(user)},
            "status_info": {st.slug: st for st in NotebookStatus.objects.all()},
        },
    )


def _slugs(kind):
    return list(NotebookStatus.objects.filter(kind=kind).values_list("slug", flat=True))


def _status_options():
    """Every status of the lab, with its group in the label when it is not a lab-wide one."""
    rows = NotebookStatus.objects.select_related("research_group").order_by(
        "research_group__name", "position", "id"
    )
    return [
        (s.slug, s.name if s.research_group is None else f"{s.name} ({s.research_group.name})")
        for s in rows
        if s.kind != NotebookStatus.Kind.ARCHIVED
    ]


def delete_attachment_files(attachments):
    """Remove the stored files of attachments. Returns how many could not be removed.

    The database rows are the record; a file that cannot be unlinked (for example
    owned by another account) is reported, never fatal.
    """
    left = 0
    for attachment in attachments:
        if not attachment.file:
            continue
        try:
            attachment.file.storage.delete(attachment.file.name)
        except Exception:
            left += 1
    return left


def purge_entry(entry):
    """Delete an entry for good, with its attachments' files. Returns files left on disk."""
    left = delete_attachment_files(list(entry.attachments.all()))
    entry.delete()
    return left


@login_required
@require_POST
def notebook_dashboard_batch_api(request):
    """Apply one action to several entries; entries the user cannot edit are skipped."""
    try:
        data = json.loads(request.body or b"{}")
        ids = [int(pk) for pk in data.get("ids") or []]
    except (ValueError, TypeError):
        return JsonResponse({"status": "error", "message": "Invalid request."}, status=400)

    if not ids or len(ids) > BATCH_LIMIT:
        return JsonResponse({"status": "error", "message": f"Select 1 to {BATCH_LIMIT} entries."}, status=400)

    action = data.get("action")
    value = data.get("value")

    # Entries in the trash are not "visible"; restore and delete-for-good act on them.
    if action in {"restore", "purge"}:
        trashed = list(trashed_notebook_entries_for_user(request.user).filter(pk__in=ids))
        leftover = 0
        with transaction.atomic():
            for entry in trashed:
                if action == "restore":
                    entry.deleted_at = None
                    entry.deleted_by = None
                    entry.save(update_fields=["deleted_at", "deleted_by"])
                else:
                    leftover += purge_entry(entry)
        payload = {"status": "success", "changed": len(trashed), "skipped": len(ids) - len(trashed)}
        if leftover:
            payload["files_left_on_disk"] = leftover
        return JsonResponse(payload)

    entries = list(visible_notebook_entries_for_user(request.user).filter(pk__in=ids))

    # Pins are personal: any visible entry can be pinned.
    if action in {"pin", "unpin"}:
        for entry in entries:
            if action == "pin":
                NotebookPin.objects.get_or_create(user=request.user, entry=entry)
            else:
                NotebookPin.objects.filter(user=request.user, entry=entry).delete()
        return JsonResponse({"status": "success", "changed": len(entries), "skipped": len(ids) - len(entries)})

    editable = [e for e in entries if can_edit_notebook_entry(request.user, e)]

    try:
        with transaction.atomic():
            if action == "status":
                if not NotebookStatus.objects.filter(slug=value).exists():
                    raise ValidationError("Unknown status.")
                # Each entry only takes statuses from its own list.
                editable = [
                    e for e in editable if notebook_taxonomy.resolve_status_slug(e, value)
                ]
                for entry in editable:
                    entry.status = value
                    entry.save(update_fields=["status", "updated_at"])
            elif action == "trash":
                # Sharing never gives the right to remove somebody else's entry.
                editable = [e for e in editable if can_delete_notebook_entry(request.user, e)]
                for entry in editable:
                    entry.deleted_at = timezone.now()
                    entry.deleted_by = request.user
                    entry.save(update_fields=["deleted_at", "deleted_by"])
                    # The page can no longer reach the lock API once the entry is hidden.
                    NotebookEditLock.objects.filter(entry=entry).delete()
            elif action == "archive":
                for entry in editable:
                    entry.status = "archived"
                    entry.save(update_fields=["status", "updated_at"])
            elif action == "add_tag":
                name = str(value or "").strip().lstrip("#")
                if not TAG_RE.match(name):
                    raise ValidationError("Tags use letters, numbers and . + # / : - only.")
                tag, _ = get_or_create_active_tag(name)
                for entry in editable:
                    entry.shared_tags.add(tag)
            else:
                raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return JsonResponse({"status": "error", "message": " ".join(exc.messages)}, status=400)

    return JsonResponse(
        {"status": "success", "changed": len(editable), "skipped": len(ids) - len(editable)}
    )
