"""The viewer's own agenda for today and the rest of the week (ELN dashboard card)."""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from bench.models import Booking
from core.models import NotebookStep
from core.permissions.notebook import visible_notebook_entries_for_user

STEP_COLOR = "#7c3aed"
LIMIT = 12


def _week_end(now):
    """Start of the next Monday, in the local time zone."""
    local = timezone.localtime(now)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=7 - midnight.weekday())


def agenda(user, now=None):
    """Upcoming bookings and step deadlines of ``user``, ``today`` first."""
    now = now or timezone.now()
    end = _week_end(now)
    tomorrow = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    items = []

    bookings = (
        Booking.objects.active()
        .filter(user=user, end__gt=now, start__lt=end, resource__is_active=True)
        .select_related("resource", "notebook_entry")
        .order_by("start")
    )
    for b in bookings:
        items.append(
            {
                "kind": "booking",
                "when": b.start,
                "until": b.end,
                "title": b.resource.name + (f" · {b.title}" if b.title else ""),
                "url": reverse("lab_calendar"),
                "color": b.resource.color,
                "icon": "bi-cpu",
            }
        )

    steps = (
        NotebookStep.objects.filter(
            entry__in=visible_notebook_entries_for_user(user).filter(author=user),
            finished=False,
            deadline__lt=end,
        )
        .select_related("entry")
        .order_by("deadline")
    )
    for s in steps:
        items.append(
            {
                "kind": "step",
                "when": s.deadline,
                "until": None,
                "title": s.body,
                "url": reverse("notebook_entry", args=[s.entry_id]),
                "color": STEP_COLOR,
                "icon": "bi-check2-square",
                "overdue": s.deadline < now,
            }
        )

    items.sort(key=lambda i: i["when"])
    today = [i for i in items if i["when"] < tomorrow]  # includes overdue steps
    later = [i for i in items if i["when"] >= tomorrow]
    return {"today": today[:LIMIT], "later": later[:LIMIT], "total": len(items)}
