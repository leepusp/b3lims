import csv

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

from core.context import base_context
from core.models.activity import ActivityLog
from core.services import activity

PAGE_SIZE = 50


def _filtered(request):
    qs = activity.visible_to(request.user)
    params = request.GET
    q = (params.get("q") or "").strip()
    entity = params.get("entity") or ""
    verb = params.get("verb") or ""
    actor = params.get("actor") or ""
    start = parse_date(params.get("from") or "")
    end = parse_date(params.get("to") or "")

    if q:
        qs = qs.filter(Q(entity_label__icontains=q) | Q(summary__icontains=q))
    if entity in activity.ENTITY_LABELS:
        qs = qs.filter(entity_type=entity)
    if verb in ActivityLog.Verb.values:
        qs = qs.filter(verb=verb)
    if actor.isdigit() and request.user.is_superuser:
        qs = qs.filter(actor_id=int(actor))
    if start:
        qs = qs.filter(updated_at__date__gte=start)
    if end:
        qs = qs.filter(updated_at__date__lte=end)

    return qs.select_related("actor")


@login_required
def activity_history(request):
    """Searchable history of everything added, changed or removed."""
    qs = _filtered(request)

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="activity-history.csv"'
        writer = csv.writer(response)

        writer.writerow(["When", "Who", "Action", "Type", "Name", "Times"])
        for row in qs[:5000]:
            writer.writerow([
                row.updated_at.isoformat(timespec="seconds"), row.actor_name, row.verb,
                activity.ENTITY_LABELS.get(row.entity_type, row.entity_type), row.entity_label, row.count,
            ])

        return response

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))

    for row in page:
        row.type_label = activity.ENTITY_LABELS.get(row.entity_type, row.entity_type)

    context = base_context(request)
    keep = request.GET.copy()

    keep.pop("page", None)
    context.update({
        "page": page,
        "entity_options": activity.ENTITY_GROUPS,
        "verb_options": ActivityLog.Verb.choices,
        "actor_options": (
            get_user_model().objects.filter(activity_logs__isnull=False).distinct().order_by("username")
            if request.user.is_superuser else []
        ),
        "entity_labels": activity.ENTITY_LABELS,
        "filters": request.GET,
        "query": keep.urlencode(),
    })

    return render(request, "internal/calendar/history.html", context)
