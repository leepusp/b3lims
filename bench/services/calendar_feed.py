"""Events shown in the Lab Calendar, in the shape FullCalendar reads.

Layers: ``bookings`` (equipment), ``steps`` (ELN steps with a deadline, the
viewer's own, still open) and ``samples`` (sample events the viewer may see).
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from bench.models import Booking
from bench.services.ics import google_link
from bench.services.layers import styles_for
from bench.permissions.scheduling import can_manage_booking
from core.models import NotebookStep
from core.models.events.model import Event
from core.permissions.workspace import visible_workspace_events_for_user

LAYERS = ("bookings", "steps", "samples")
MAX_RANGE = timedelta(days=100)
SAMPLE_ROW_LIMIT = 5000
SAMPLE_LIST_LIMIT = 40


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def booking_event(booking, user):
    can_edit = can_manage_booking(user, booking)
    entry = booking.notebook_entry
    event = {
        "id": f"booking:{booking.pk}",
        "title": f"{booking.resource.name} · {booking.title or _name(booking.user)}",
        "start": booking.start.isoformat(),
        "end": booking.end.isoformat(),
        "color": booking.resource.color,
        "editable": can_edit,
        "extendedProps": {
            "kind": "booking",
            "booking_id": booking.pk,
            "resource_id": booking.resource_id,
            "resource": booking.resource.name,
            "who": _name(booking.user),
            "note": booking.note,
            "series": bool(booking.recurrence_id),
            "can_edit": can_edit,
            "entry": (
                {"title": entry.title, "url": reverse("notebook_entry", args=[entry.pk])}
                if entry is not None
                else None
            ),
        },
    }
    event["extendedProps"]["google_url"] = google_link(event)
    event["extendedProps"]["ics_url"] = reverse("bench:booking_ics", args=[booking.pk])
    return event


def feed(user, start, end, layers=LAYERS, resource_ids=None):
    """Events between start and end (aware datetimes) for this viewer."""
    if end - start > MAX_RANGE:
        end = start + MAX_RANGE
    layers = [layer for layer in layers if layer in LAYERS]
    events = []
    style = styles_for(user)

    if "bookings" in layers:
        qs = (
            Booking.objects.active()
            .overlapping(start, end)
            .select_related("resource", "user", "notebook_entry")
            .filter(resource__is_active=True)
        )
        if resource_ids:
            qs = qs.filter(resource_id__in=resource_ids)
        events.extend(booking_event(b, user) for b in qs)

    if "steps" in layers:
        from core.permissions.notebook import visible_notebook_entries_for_user

        steps = (
            NotebookStep.objects.filter(
                entry__in=visible_notebook_entries_for_user(user).filter(author=user),
                finished=False,
                deadline__gte=start,
                deadline__lt=end,
            )
            .select_related("entry")
            .order_by("deadline")
        )
        for step in steps:
            events.append(
                {
                    "id": f"step:{step.pk}",
                    "title": f"Step: {step.body}",
                    "start": step.deadline.isoformat(),
                    "color": style["steps"]["color"],
                    "url": reverse("notebook_entry", args=[step.entry_id]),
                    "editable": False,
                    "extendedProps": {"kind": "step", "entry": step.entry.title},
                }
            )

    if "samples" in layers:
        # One chip per day and event type ("Entrada · 38 samples"): the history
        # of a busy day would otherwise bury everything else.
        rows = (
            visible_workspace_events_for_user(user)
            .filter(timestamp__gte=start, timestamp__lt=end)
            .order_by("timestamp")
            .values_list("timestamp", "event_type", "sample__sample_id")[:SAMPLE_ROW_LIMIT]
        )
        labels = dict(Event._meta.get_field("event_type").choices)
        groups = {}
        for stamp, kind, sample_id in rows:
            day = timezone.localtime(stamp).date()
            groups.setdefault((day, kind), []).append(sample_id)
        for (day, kind), ids in sorted(groups.items()):
            label = str(labels.get(kind, kind))
            count = len(ids)
            events.append(
                {
                    "id": f"samples:{day.isoformat()}:{kind}",
                    "title": f"{label} · {count} sample{'s' if count != 1 else ''}",
                    "start": day.isoformat(),
                    "allDay": True,
                    "color": style["samples"]["color"],
                    "editable": False,
                    "extendedProps": {
                        "kind": "sample_group",
                        "count": count,
                        "sample_ids": ids[:SAMPLE_LIST_LIMIT],
                        "more": max(0, count - SAMPLE_LIST_LIMIT),
                    },
                }
            )
    return events
