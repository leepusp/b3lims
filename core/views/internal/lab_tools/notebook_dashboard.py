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
from core.models.lab_tools.notebook_composer import NotebookPin, NotebookStep, NotebookTag
from core.permissions.notebook import can_edit_notebook_entry, visible_notebook_entries_for_user
from core.services.notebook_composer import TAG_RE


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
    qs = visible_notebook_entries_for_user(user)

    filters = {
        "q": (params.get("q") or "").strip(),
        "type": params.get("type") or "",
        "status": params.get("status") or "",
        "owner": params.get("owner") or "",
        "tag": (params.get("tag") or "").strip().lower(),
        "state": params.get("state") or "active",
        "sort": params.get("sort") if params.get("sort") in SORTS else "modified",
    }

    if filters["state"] == "archived":
        qs = qs.filter(status="archived")
    elif filters["state"] != "all":
        filters["state"] = "active"
        qs = qs.exclude(status="archived")

    if filters["q"]:
        q = filters["q"]
        condition = (
            Q(title__icontains=q)
            | Q(custom_id__icontains=q)
            | Q(project__icontains=q)
            | Q(content__icontains=q)
            | Q(tags__name__icontains=q.lstrip("#"))
        )
        if q.lstrip("#").isdigit():
            condition |= Q(pk=int(q.lstrip("#")))
        qs = qs.filter(condition)

    if filters["type"] in dict(NotebookEntry.ENTRY_TYPE_CHOICES):
        qs = qs.filter(entry_type=filters["type"])
    else:
        filters["type"] = ""

    if filters["status"] in dict(NotebookEntry.STATUS_CHOICES):
        qs = qs.filter(status=filters["status"])
    else:
        filters["status"] = ""

    if filters["owner"] == "me":
        qs = qs.filter(author=user)
    elif filters["owner"] == "others":
        qs = qs.exclude(author=user)
    else:
        filters["owner"] = ""

    if filters["tag"]:
        qs = qs.filter(tags__name=filters["tag"])

    qs = (
        qs.distinct()
        .select_related("author")
        .prefetch_related("tags")
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
        NotebookTag.objects.filter(entries__in=visible)
        .annotate(n=Count("entries", distinct=True))
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
            "statuses": NotebookEntry.STATUS_CHOICES,
            "pinned": pinned,
            "tag_cloud": tag_cloud,
            "stats": {
                "visible": visible.exclude(status="archived").count(),
                "mine": mine.exclude(status="archived").count(),
                "in_progress": mine.filter(status="in_progress").count(),
                "to_review": visible.filter(status="completed").count(),
                "overdue": open_steps.filter(deadline__lt=now).count(),
            },
            "due_steps": open_steps[:6],
            "now": now,
            "recent": mine.order_by("-updated_at")[:5],
            "notebook_entry_templates": _notebook_entry_templates(),
            "status_badges": {
                "draft": "text-bg-light",
                "in_progress": "text-bg-primary",
                "completed": "text-bg-success",
                "reviewed": "text-bg-info",
                "archived": "text-bg-secondary",
            },
        },
    )


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
                if value not in dict(NotebookEntry.STATUS_CHOICES):
                    raise ValidationError("Unknown status.")
                for entry in editable:
                    entry.status = value
                    entry.save(update_fields=["status", "updated_at"])
            elif action == "archive":
                for entry in editable:
                    entry.status = "archived"
                    entry.save(update_fields=["status", "updated_at"])
            elif action == "add_tag":
                name = str(value or "").strip().lstrip("#").lower()
                if not TAG_RE.match(name):
                    raise ValidationError("Tags use letters, numbers and . + # / : - only.")
                tag, _ = NotebookTag.objects.get_or_create(name=name)
                for entry in editable:
                    entry.tags.add(tag)
            else:
                raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return JsonResponse({"status": "error", "message": " ".join(exc.messages)}, status=400)

    return JsonResponse(
        {"status": "success", "changed": len(editable), "skipped": len(ids) - len(editable)}
    )
