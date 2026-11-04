"""iCalendar (.ics) and "Add to Google Calendar" links for Lab Calendar events.

Times are written in UTC, so no VTIMEZONE block is needed and every calendar
app (Google, Outlook, Apple) reads them the same way. Nothing here reaches the
internet: the person downloads the file or opens the prefilled Google link.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlencode

from django.utils.dateparse import parse_datetime

PRODID = "-//CEPID B3//B3 LIMS Lab Calendar//EN"
POINT_EVENT = timedelta(minutes=30)  # step deadlines and sample events have no end


def _utc(value) -> datetime:
    if isinstance(value, str):
        value = parse_datetime(value)
    return value.astimezone(dt_timezone.utc)


def _stamp(value) -> str:
    return _utc(value).strftime("%Y%m%dT%H%M%SZ")


def escape_text(value) -> str:
    text = str(value or "")
    for old, new in (("\\", "\\\\"), (";", "\\;"), (",", "\\,")):
        text = text.replace(old, new)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """Fold a content line at 75 octets (RFC 5545 section 3.1), never inside a character."""
    out, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        limit = 75 if not out else 74  # continuation lines start with a space
        if size + width > limit:
            out.append(current)
            current, size = char, width
        else:
            current += char
            size += width
    out.append(current)
    return "\r\n ".join(out)


def _times(event):
    start = _utc(event["start"])
    end = _utc(event["end"]) if event.get("end") else start + POINT_EVENT
    return start, end


def _details(event) -> str:
    props = event.get("extendedProps") or {}
    parts = []
    if props.get("who"):
        parts.append(f"Booked by {props['who']}")
    if props.get("note"):
        parts.append(props["note"])
    return "\n".join(parts)


def calendar_text(events, name="B3 LIMS Lab Calendar", now=None) -> str:
    """Build a VCALENDAR from FullCalendar-shaped event dicts."""
    stamp = _stamp(now or datetime.now(dt_timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(name)}",
    ]
    for event in events:
        start, end = _times(event)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event['id'].replace(':', '-')}@b3lims",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_stamp(start)}",
            f"DTEND:{_stamp(end)}",
            f"SUMMARY:{escape_text(event['title'])}",
        ]
        details = _details(event)
        if details:
            lines.append(f"DESCRIPTION:{escape_text(details)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def google_link(event) -> str:
    """A prefilled "new event" page on Google Calendar; the person confirms it there."""
    start, end = _times(event)
    query = {
        "action": "TEMPLATE",
        "text": event["title"],
        "dates": f"{_stamp(start)}/{_stamp(end)}",
    }
    details = _details(event)
    if details:
        query["details"] = details
    return "https://calendar.google.com/calendar/render?" + urlencode(query)
