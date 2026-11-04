"""Events shown in the Lab Calendar, in the shape FullCalendar reads.

Layers: ``bookings`` (equipment), ``steps`` (ELN steps with a deadline, the
viewer's own, still open) and ``samples`` (sample events the viewer may see).
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse

from bench.models import Booking
from bench.permissions.scheduling import can_manage_booking
from core.models import NotebookStep
from core.models.events.model import Event
from core.permissions.workspace import visible_workspace_events_for_user

LAYERS = ("bookings", "steps", "samples")
MAX_RANGE = timedelta(days=100)
STEP_COLOR = "#7c3aed"
SAMPLE_COLORS = {
    "entry": "#198754",
    "qc_check": "#b8860b",
    "freeze": "#0aa2c0",
    "thaw": "#0aa2c0",
    "transfer": "#6c757d",
}


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def booking_event(booking, user):
    can_edit = can_manage_booking(user, booking)
    entry = booking.notebook_entry
    return {
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


def feed(user, start, end, layers=LAYERS, resource_ids=None):
    """Events between start and end (aware datetimes) for this viewer."""
    if end - start > MAX_RANGE:
        end = start + MAX_RANGE
    layers = [layer for layer in layers if layer in LAYERS]
    events = []

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
                    "color": STEP_COLOR,
                    "url": reverse("notebook_entry", args=[step.entry_id]),
                    "editable": False,
                    "extendedProps": {"kind": "step", "entry": step.entry.title},
                }
            )

    if "samples" in layers:
        sample_events = (
            visible_workspace_events_for_user(user)
            .filter(timestamp__gte=start, timestamp__lt=end)
            .select_related("sample", "performed_by")[:300]
        )
        for ev in sample_events:
            events.append(
                {
                    "id": f"sample:{ev.pk}",
                    "title": f"{ev.get_event_type_display()} · {ev.sample.sample_id}",
                    "start": ev.timestamp.isoformat(),
                    "color": SAMPLE_COLORS.get(ev.event_type, "#6c757d"),
                    "editable": False,
                    "extendedProps": {"kind": "sample", "who": _name(ev.performed_by)},
                }
            )
    return events
