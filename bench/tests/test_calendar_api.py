"""Lab Calendar JSON endpoints: feed, create, move, cancel."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bench.models import BookableResource, Booking
from core.models import NotebookEntry, NotebookStep, ResearchGroup


class CalendarApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ana = User.objects.create_user("cal-ana", password="x")
        cls.bob = User.objects.create_user("cal-bob", password="x")
        cls.outsider = User.objects.create_user("cal-out", password="x")
        cls.group = ResearchGroup.objects.create(name="Cal Group", coordinator=cls.ana)
        cls.group.members.add(cls.bob)
        cls.scope = BookableResource.objects.create(
            name="Microscope", research_group=cls.group, color="#aa3300", max_minutes=120
        )

    def setUp(self):
        self.client.force_login(self.ana)
        base = (timezone.now() + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
        self.start, self.end = base, base + timedelta(hours=1)

    def post(self, name, payload, *args):
        return self.client.post(
            reverse(f"bench:{name}", args=args), json.dumps(payload), content_type="application/json"
        )

    def book(self, **extra):
        payload = {
            "resource": self.scope.pk,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "title": "Imaging",
        }
        payload.update(extra)
        return self.post("booking_create", payload)

    def feed(self, **params):
        params.setdefault("start", (self.start - timedelta(days=1)).isoformat())
        params.setdefault("end", (self.end + timedelta(days=1)).isoformat())
        response = self.client.get(reverse("bench:calendar_events"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_create_and_see_a_booking_in_the_feed(self):
        self.assertEqual(self.book().json()["created"], 1)
        [event] = self.feed()
        self.assertEqual(event["extendedProps"]["kind"], "booking")
        self.assertEqual(event["color"], "#aa3300")
        self.assertTrue(event["editable"])
        self.assertIn("Microscope", event["title"])

    def test_rules_come_back_as_a_list_with_422(self):
        response = self.book(end=(self.start + timedelta(hours=5)).isoformat())
        self.assertEqual(response.status_code, 422)
        self.assertEqual([v["code"] for v in response.json()["violations"]], ["too_long"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_overlap_is_refused_and_recurrence_creates_a_series(self):
        self.book()
        clash = self.book()
        self.assertEqual(clash.status_code, 422)
        self.assertIn("overlap", [v["code"] for v in clash.json()["violations"]])
        series = self.book(
            start=(self.start + timedelta(days=1)).isoformat(),
            end=(self.end + timedelta(days=1)).isoformat(),
            recurrence={"frequency": "daily", "count": 3},
        )
        self.assertEqual(series.json()["created"], 3)

    def test_only_people_who_may_book_can_book(self):
        self.client.force_login(self.outsider)
        response = self.book()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["violations"][0]["code"], "permission")

    def test_move_checks_rules_and_ownership(self):
        self.book()
        booking = Booking.objects.get()
        later = {"start": (self.start + timedelta(hours=2)).isoformat(), "end": (self.end + timedelta(hours=2)).isoformat()}
        self.assertEqual(self.post("booking_move", later, booking.pk).status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.start, self.start + timedelta(hours=2))
        self.client.force_login(self.bob)  # member, not the owner or coordinator
        self.assertEqual(self.post("booking_move", later, booking.pk).status_code, 422)

    def test_cancel_one_or_the_series(self):
        self.book(recurrence={"frequency": "daily", "count": 3})
        first = Booking.objects.order_by("start").first()
        self.assertEqual(self.post("booking_cancel", {}, first.pk).json()["cancelled"], 1)
        second = Booking.objects.active().order_by("start").first()
        self.assertEqual(self.post("booking_cancel", {"whole_series": True}, second.pk).json()["cancelled"], 2)
        self.assertEqual(self.feed(), [])

    def test_steps_layer_shows_only_my_open_steps_with_a_deadline(self):
        mine = NotebookEntry.objects.create(title="Mine", author=self.ana)
        theirs = NotebookEntry.objects.create(title="Theirs", author=self.bob, visibility="lab")
        NotebookStep.objects.create(entry=mine, body="Image gel", deadline=self.start)
        NotebookStep.objects.create(entry=mine, body="Done one", deadline=self.start, finished=True)
        NotebookStep.objects.create(entry=theirs, body="Not mine", deadline=self.start)
        titles = [e["title"] for e in self.feed(layers="steps")]
        self.assertEqual(titles, ["Step: Image gel"])

    def test_layers_and_resource_filters(self):
        self.book()
        self.assertEqual(self.feed(layers="steps"), [])
        self.assertEqual(len(self.feed(resources=str(self.scope.pk))), 1)
        self.assertEqual(self.feed(resources="999"), [])

    def test_bad_dates_and_login(self):
        self.assertEqual(self.client.get(reverse("bench:calendar_events"), {"start": "x", "end": "y"}).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("bench:calendar_events")).status_code, 302)

    def test_resources_endpoint_lists_who_can_book_and_my_entries(self):
        NotebookEntry.objects.create(title="Gel A", author=self.ana)
        data = self.client.get(reverse("bench:calendar_resources")).json()
        self.assertEqual([r["name"] for r in data["resources"]], ["Microscope"])
        self.assertTrue(data["resources"][0]["can_book"])
        self.assertEqual([e["title"] for e in data["entries"]], ["Gel A"])


class CalendarPageTests(TestCase):
    def test_page_renders_with_the_endpoints_and_no_sample_dump(self):
        user = get_user_model().objects.create_user("cal-page", password="x")
        self.client.force_login(user)
        html = self.client.get(reverse("lab_calendar")).content.decode()
        for name in ("calendar_events", "calendar_resources", "booking_create"):
            self.assertIn(reverse(f"bench:{name}"), html)
        self.assertIn("lab_calendar_v1.js", html)
        self.assertIn("csrfmiddlewaretoken", html)


class CalendarIcsTests(CalendarApiTests):
    def test_booking_ics_and_google_link(self):
        booking = self.book().json()
        pk = booking["id"] if "id" in booking else Booking.objects.get().pk
        response = self.client.get(reverse("bench:booking_ics", args=[pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/calendar", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn("SUMMARY:", body)
        self.assertTrue(body.endswith("\r\n"))
        events = self.client.get(
            reverse("bench:calendar_events"),
            {"start": (self.start - timedelta(days=1)).isoformat(), "end": (self.end + timedelta(days=1)).isoformat()},
        ).json()
        props = events[0]["extendedProps"]
        self.assertTrue(props["google_url"].startswith("https://calendar.google.com/calendar/render?"))
        self.assertIn(f"/bookings/{pk}/event.ics", props["ics_url"])

    def test_view_export(self):
        self.book()
        response = self.client.get(
            reverse("bench:calendar_ics"),
            {"start": (self.start - timedelta(days=1)).isoformat(), "end": (self.end + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count("BEGIN:VEVENT"), 1)

    def test_export_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("bench:calendar_ics")).status_code, 302)

    def test_line_folding_and_escaping(self):
        from bench.services.ics import escape_text, fold

        self.assertEqual(escape_text("a,b;c\nd"), "a\\,b\\;c\\nd")
        for line in fold("X" * 200 + "ç" * 50).split("\r\n"):
            self.assertLessEqual(len(line.encode()), 75)


class SampleHistoryGroupingTests(CalendarApiTests):
    class FakeRows:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, **kw):
            return self

        def order_by(self, *a):
            return self

        def values_list(self, *a):
            return self.rows

    def test_busy_day_becomes_one_chip_per_type(self):
        from unittest import mock

        stamp = self.start
        rows = [(stamp, "entry", f"S-{i}") for i in range(60)] + [(stamp, "transfer", "S-1")]
        with mock.patch("bench.services.calendar_feed.visible_workspace_events_for_user", return_value=self.FakeRows(rows)):
            events = self.client.get(
                reverse("bench:calendar_events"),
                {"start": (stamp - timedelta(days=2)).isoformat(), "end": (stamp + timedelta(days=2)).isoformat(), "layers": "samples"},
            ).json()
            exported = self.client.get(
                reverse("bench:calendar_ics"),
                {"start": (stamp - timedelta(days=2)).isoformat(), "end": (stamp + timedelta(days=2)).isoformat()},
            )
        self.assertEqual(len(events), 2)
        big = next(e for e in events if e["extendedProps"]["count"] == 60)
        self.assertTrue(big["allDay"])
        self.assertEqual(len(big["extendedProps"]["sample_ids"]), 40)
        self.assertEqual(big["extendedProps"]["more"], 20)
        self.assertEqual(exported.status_code, 200)
