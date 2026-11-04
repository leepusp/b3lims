"""Booking rules for the Lab Calendar (roadmap step 2.1).

``validate_booking`` returns every rule a booking breaks, in a fixed order, so
the booking form can list them all. ``create_booking`` expands recurrences and
saves the whole series or nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bench.models import BookableResource, Booking
from bench.permissions.scheduling import can_book_resource, can_manage_booking


MAX_OCCURRENCES = 104
FREQUENCIES = ("daily", "weekly")


@dataclass(frozen=True)
class RuleViolation:
    code: str
    message: str
    occurrence: int | None = None

    def as_dict(self):
        return {"code": self.code, "message": self.message, "occurrence": self.occurrence}


class BookingRuleError(ValidationError):
    """Raised when a booking breaks one or more rules."""

    def __init__(self, violations):
        self.violations = list(violations)
        super().__init__([v.message for v in self.violations])


# --------------------------------------------------------------------------
# Recurrence
# --------------------------------------------------------------------------

def normalize_recurrence(rule, start) -> dict | None:
    """Validate a recurrence rule and return it in a canonical form.

    Accepted shape::

        {"frequency": "daily" | "weekly", "interval": 1,
         "weekdays": [0, 2],            # weekly only, Monday = 0; default: start's weekday
         "count": 4}                    # or "until": "2026-12-31"
    """
    if not rule:
        return None
    if not isinstance(rule, dict):
        raise ValidationError("Recurrence must be an object.")

    frequency = rule.get("frequency")
    if frequency not in FREQUENCIES:
        raise ValidationError("Recurrence frequency must be daily or weekly.")

    try:
        interval = int(rule.get("interval", 1))
    except (TypeError, ValueError):
        raise ValidationError("Recurrence interval must be a whole number.")
    if interval < 1:
        raise ValidationError("Recurrence interval must be at least 1.")

    has_count = rule.get("count") not in (None, "")
    has_until = rule.get("until") not in (None, "")
    if has_count == has_until:
        raise ValidationError("Recurrence needs either a count or an end date.")

    normalized = {"frequency": frequency, "interval": interval}

    if frequency == "weekly":
        weekdays = rule.get("weekdays") or [timezone.localtime(start).weekday()]
        try:
            weekdays = sorted({int(day) for day in weekdays})
        except (TypeError, ValueError):
            raise ValidationError("Weekdays must be numbers from 0 (Monday) to 6 (Sunday).")
        if any(day < 0 or day > 6 for day in weekdays):
            raise ValidationError("Weekdays must be numbers from 0 (Monday) to 6 (Sunday).")
        normalized["weekdays"] = weekdays

    if has_count:
        try:
            count = int(rule["count"])
        except (TypeError, ValueError):
            raise ValidationError("Recurrence count must be a whole number.")
        if count < 1 or count > MAX_OCCURRENCES:
            raise ValidationError(f"Recurrence count must be between 1 and {MAX_OCCURRENCES}.")
        normalized["count"] = count
    else:
        until = rule["until"]
        if isinstance(until, str):
            try:
                until = date.fromisoformat(until)
            except ValueError:
                raise ValidationError("Recurrence end date must be YYYY-MM-DD.")
        if not isinstance(until, date):
            raise ValidationError("Recurrence end date must be YYYY-MM-DD.")
        if until < timezone.localtime(start).date():
            raise ValidationError("Recurrence end date is before the first booking.")
        normalized["until"] = until.isoformat()

    return normalized


def expand_recurrence(start: datetime, end: datetime, rule: dict | None) -> list[tuple[datetime, datetime]]:
    """Return the (start, end) of every occurrence, the first one included."""
    if end <= start:
        return [(start, end)]
    rule = normalize_recurrence(rule, start)
    if rule is None:
        return [(start, end)]

    local_start = timezone.localtime(start)
    tz = local_start.tzinfo
    clock = local_start.time()
    duration = end - start
    first_day = local_start.date()
    until = date.fromisoformat(rule["until"]) if "until" in rule else None
    count = rule.get("count")
    interval = rule["interval"]

    def occurrence(day):
        begin = datetime.combine(day, clock).replace(tzinfo=tz)
        return begin, begin + duration

    days: list[date] = []
    if rule["frequency"] == "daily":
        day = first_day
        while len(days) < MAX_OCCURRENCES:
            if until and day > until:
                break
            days.append(day)
            if count and len(days) >= count:
                break
            day += timedelta(days=interval)
    else:
        weekdays = rule["weekdays"]
        week_start = first_day - timedelta(days=first_day.weekday())
        stop = False
        while not stop and len(days) < MAX_OCCURRENCES:
            for weekday in weekdays:
                day = week_start + timedelta(days=weekday)
                if day < first_day:
                    continue
                if until and day > until:
                    stop = True
                    break
                days.append(day)
                if (count and len(days) >= count) or len(days) >= MAX_OCCURRENCES:
                    stop = True
                    break
            week_start += timedelta(weeks=interval)

    return [occurrence(day) for day in days]


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def validate_booking(
    resource: BookableResource,
    user,
    start: datetime,
    end: datetime,
    *,
    note: str = "",
    now: datetime | None = None,
    exclude_ids=(),
    new_bookings: int = 1,
    occurrence: int | None = None,
) -> list[RuleViolation]:
    """Return every rule this booking breaks (an empty list means it is allowed).

    Order: permission, end after start, past start, note, maximum length,
    booking window, open bookings per user, overlap.
    """
    now = now or timezone.now()
    violations: list[RuleViolation] = []

    def fail(code, message):
        violations.append(RuleViolation(code, message, occurrence))

    if not can_book_resource(user, resource):
        fail("permission", f"You cannot book {resource.name}.")

    if end <= start:
        fail("end_before_start", "The end must be after the start.")
        return violations

    if start < now and not resource.users_can_book_in_past:
        fail("in_past", "This layer cannot be booked in the past.")

    if resource.requires_note and not (note or "").strip():
        fail("note_required", "This layer requires a note describing the use.")

    minutes = (end - start).total_seconds() / 60
    if resource.max_minutes and minutes > resource.max_minutes:
        fail(
            "too_long",
            f"Bookings are limited to {resource.max_minutes} minutes; this one has {int(minutes)}.",
        )

    if resource.booking_window_days and start > now + timedelta(days=resource.booking_window_days):
        fail(
            "outside_window",
            f"Bookings open {resource.booking_window_days} days ahead.",
        )

    if resource.max_slots and new_bookings:
        open_bookings = (
            Booking.objects.active()
            .filter(resource=resource, user=user, end__gt=now)
            .exclude(pk__in=list(exclude_ids))
            .count()
        )
        if open_bookings + new_bookings > resource.max_slots:
            fail(
                "too_many_bookings",
                f"You can hold {resource.max_slots} open bookings on this layer; "
                f"you have {open_bookings} and are adding {new_bookings}.",
            )

    if not resource.can_overlap:
        clash = (
            Booking.objects.active()
            .filter(resource=resource)
            .overlapping(start, end)
            .exclude(pk__in=list(exclude_ids))
            .select_related("user")
            .first()
        )
        if clash is not None:
            who = clash.user.get_full_name() or clash.user.get_username()
            fail(
                "overlap",
                f"Overlaps a booking by {who}, "
                f"{timezone.localtime(clash.start):%H:%M}–{timezone.localtime(clash.end):%H:%M}.",
            )

    return violations


def _series_overlaps(occurrences):
    ordered = sorted(enumerate(occurrences), key=lambda item: item[1][0])
    clashes = []
    for (i, (s1, e1)), (j, (s2, e2)) in zip(ordered, ordered[1:]):
        if s2 < e1:
            clashes.append(j)
    return clashes


@transaction.atomic
def create_booking(
    resource: BookableResource,
    user,
    start: datetime,
    end: datetime,
    *,
    title: str = "",
    note: str = "",
    notebook_entry=None,
    research_group=None,
    recurrence: dict | None = None,
    now: datetime | None = None,
) -> list[Booking]:
    """Create one booking or a recurring series; all of it or nothing.

    The resource row is locked first, so two people booking the same
    equipment at the same moment are checked one after the other.
    """
    resource = BookableResource.objects.select_for_update().get(pk=resource.pk)
    now = now or timezone.now()
    rule = normalize_recurrence(recurrence, start)
    occurrences = expand_recurrence(start, end, rule)

    violations: list[RuleViolation] = []
    for index, (occ_start, occ_end) in enumerate(occurrences):
        violations.extend(
            validate_booking(
                resource,
                user,
                occ_start,
                occ_end,
                note=note,
                now=now,
                new_bookings=len(occurrences) if index == 0 else 0,
                occurrence=index if rule else None,
            )
        )
    if not resource.can_overlap:
        for index in _series_overlaps(occurrences):
            violations.append(
                RuleViolation("overlap", "Occurrences of this series overlap each other.", index)
            )

    unique = []
    seen = set()
    for violation in violations:
        key = (violation.code, violation.message)
        if violation.code in ("permission", "too_many_bookings", "note_required") and key in seen:
            continue
        seen.add(key)
        unique.append(violation)
    if unique:
        raise BookingRuleError(unique)

    recurrence_id = uuid.uuid4() if rule else None
    bookings = [
        Booking(
            resource=resource,
            user=user,
            research_group=research_group,
            title=title,
            note=note,
            start=occ_start,
            end=occ_end,
            notebook_entry=notebook_entry,
            exclusive=not resource.can_overlap,
            recurrence_id=recurrence_id,
            recurrence_index=(index + 1) if rule else None,
            recurrence_rule=rule,
        )
        for index, (occ_start, occ_end) in enumerate(occurrences)
    ]
    for booking in bookings:
        booking.save()
    return bookings


@transaction.atomic
def move_booking(booking: Booking, user, start: datetime, end: datetime, *, now=None) -> Booking:
    """Change the time of one booking, re-checking every rule."""
    if not can_manage_booking(user, booking):
        raise BookingRuleError([RuleViolation("permission", "You cannot change this booking.")])
    resource = BookableResource.objects.select_for_update().get(pk=booking.resource_id)
    violations = validate_booking(
        resource,
        booking.user,
        start,
        end,
        note=booking.note,
        now=now,
        exclude_ids=[booking.pk],
        new_bookings=1,
    )
    violations = [v for v in violations if v.code != "permission"]
    if violations:
        raise BookingRuleError(violations)
    booking.start, booking.end = start, end
    booking.save(update_fields=["start", "end", "updated_at"])
    return booking


@transaction.atomic
def cancel_booking(booking: Booking, user, *, now=None, whole_series=False) -> list[Booking]:
    """Cancel one booking (or the rest of its series) if the rules allow it."""
    now = now or timezone.now()
    if not can_manage_booking(user, booking):
        raise BookingRuleError([RuleViolation("permission", "You cannot cancel this booking.")])

    resource = booking.resource
    if not resource.is_cancellable:
        raise BookingRuleError([RuleViolation("not_cancellable", "Bookings on this layer cannot be cancelled.")])

    if whole_series and booking.recurrence_id:
        targets = list(
            Booking.objects.active().filter(recurrence_id=booking.recurrence_id, start__gte=booking.start)
        )
    else:
        targets = [booking]

    deadline = timedelta(minutes=resource.cancel_minutes)
    for target in targets:
        if resource.cancel_minutes and target.start - now < deadline:
            raise BookingRuleError(
                [
                    RuleViolation(
                        "too_late_to_cancel",
                        f"Cancel at least {resource.cancel_minutes} minutes before the start.",
                    )
                ]
            )

    for target in targets:
        target.cancelled_at = now
        target.cancelled_by = user
        target.save(update_fields=["cancelled_at", "cancelled_by", "updated_at"])
    return targets
