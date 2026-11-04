"""JSON endpoints behind the Lab Calendar screen."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from bench.models import BookableResource, Booking
from bench.permissions.scheduling import can_book_resource
from bench.services import calendar_feed, ics
from bench.services.layers import styles_for
from bench.services.booking_rules import (
    BookingRuleError,
    cancel_booking,
    create_booking,
    move_booking,
)
from core.permissions.notebook import visible_notebook_entries_for_user


def _error(message, status=400, violations=None):
    body = {"status": "error", "message": str(message)}
    if violations is not None:
        body["violations"] = [v.as_dict() for v in violations]
    return JsonResponse(body, status=status)


def _aware(value):
    parsed = parse_datetime(str(value or ""))
    if parsed is None:
        raise ValidationError("Send dates as ISO 8601 (2026-11-05T09:00).")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise ValidationError("Invalid request body.")
    if not isinstance(data, dict):
        raise ValidationError("Invalid request body.")
    return data


@login_required
@require_GET
def events(request):
    try:
        start, end = _aware(request.GET.get("start")), _aware(request.GET.get("end"))
    except ValidationError as exc:
        return _error(exc.messages[0])
    layers = [x for x in (request.GET.get("layers") or ",".join(calendar_feed.LAYERS)).split(",") if x]
    resources = [int(x) for x in (request.GET.get("resources") or "").split(",") if x.isdigit()]
    return JsonResponse(calendar_feed.feed(request.user, start, end, layers, resources), safe=False)


@login_required
@require_GET
def resources(request):
    rows = []
    for resource in BookableResource.objects.filter(is_active=True).order_by("name"):
        rows.append(
            {
                "id": resource.pk,
                "name": resource.name,
                "description": resource.description,
                "color": resource.color,
                "can_book": can_book_resource(request.user, resource),
                "requires_note": resource.requires_note,
                "max_minutes": resource.max_minutes,
            }
        )
    entries = [
        {"id": e.pk, "title": e.title or "Untitled entry"}
        for e in visible_notebook_entries_for_user(request.user)
        .filter(author=request.user)
        .order_by("-updated_at")[:30]
    ]
    return JsonResponse({"resources": rows, "entries": entries, "builtin": list(styles_for(request.user).values())})


@login_required
@require_POST
def booking_create(request):
    try:
        data = _body(request)
        resource = get_object_or_404(BookableResource, pk=data.get("resource"), is_active=True)
        entry = None
        if data.get("entry"):
            entry = get_object_or_404(
                visible_notebook_entries_for_user(request.user), pk=data["entry"]
            )
        bookings = create_booking(
            resource,
            request.user,
            _aware(data.get("start")),
            _aware(data.get("end")),
            title=str(data.get("title") or "").strip()[:255],
            note=str(data.get("note") or "").strip(),
            notebook_entry=entry,
            recurrence=data.get("recurrence") or None,
        )
    except BookingRuleError as exc:
        return _error("; ".join(v.message for v in exc.violations), 422, exc.violations)
    except ValidationError as exc:
        return _error(" ".join(exc.messages))
    return JsonResponse({"status": "success", "created": len(bookings)})


@login_required
@require_POST
def booking_move(request, booking_id):
    booking = get_object_or_404(Booking.objects.active().select_related("resource"), pk=booking_id)
    try:
        data = _body(request)
        move_booking(booking, request.user, _aware(data.get("start")), _aware(data.get("end")))
    except BookingRuleError as exc:
        return _error("; ".join(v.message for v in exc.violations), 422, exc.violations)
    except ValidationError as exc:
        return _error(" ".join(exc.messages))
    return JsonResponse({"status": "success"})


@login_required
@require_POST
def booking_cancel(request, booking_id):
    booking = get_object_or_404(Booking.objects.active().select_related("resource"), pk=booking_id)
    try:
        data = _body(request)
        cancelled = cancel_booking(booking, request.user, whole_series=bool(data.get("whole_series")))
    except BookingRuleError as exc:
        return _error("; ".join(v.message for v in exc.violations), 422, exc.violations)
    except ValidationError as exc:
        return _error(" ".join(exc.messages))
    return JsonResponse({"status": "success", "cancelled": len(cancelled)})


def _ics_response(events, filename, name):
    response = HttpResponse(ics.calendar_text(events, name=name), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def booking_ics(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.active().select_related("resource", "user", "notebook_entry"), pk=booking_id
    )
    event = calendar_feed.booking_event(booking, request.user)
    return _ics_response([event], f"booking-{booking.pk}.ics", booking.resource.name)


@login_required
@require_GET
def view_ics(request):
    """The events of the range on screen, as one .ics file."""
    try:
        start, end = _aware(request.GET.get("start")), _aware(request.GET.get("end"))
    except ValidationError as exc:
        return _error(exc.messages[0])
    layers = [x for x in (request.GET.get("layers") or ",".join(calendar_feed.LAYERS)).split(",") if x]
    resources = [int(x) for x in (request.GET.get("resources") or "").split(",") if x.isdigit()]
    events = [
        e for e in calendar_feed.feed(request.user, start, end, layers, resources)
        if e["extendedProps"].get("kind") != "sample_group"  # day summaries are not appointments
    ]
    return _ics_response(events, "b3-lims-calendar.ics", "B3 LIMS Lab Calendar")
