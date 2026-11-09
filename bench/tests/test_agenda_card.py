from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bench.models import BookableResource, Booking
from bench.services.agenda import agenda
from core.models import NotebookEntry, NotebookStep, ResearchGroup


# The card looks at the rest of the week (to the next Monday), so these tests
# run on a fixed Wednesday noon; with the real clock they failed on Sunday night.
MIDWEEK = timezone.make_aware(datetime(2026, 11, 4, 12, 0))


class AgendaCardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ana = User.objects.create_user("ag-ana", password="x")
        cls.bob = User.objects.create_user("ag-bob", password="x")
        group = ResearchGroup.objects.create(name="Ag Group", coordinator=cls.ana)
        group.members.add(cls.bob)
        cls.scope = BookableResource.objects.create(name="Microscope", research_group=group)

    def book(self, user, start, hours=1, **extra):
        return Booking.objects.create(
            resource=self.scope, user=user, start=start, end=start + timedelta(hours=hours), exclusive=False, **extra
        )

    def test_only_own_active_bookings_in_the_week(self):
        now = MIDWEEK
        mine = self.book(self.ana, now + timedelta(minutes=30), title="Imaging")
        self.book(self.bob, now + timedelta(hours=3))
        self.book(self.ana, now + timedelta(days=30))
        cancelled = self.book(self.ana, now + timedelta(hours=5))
        cancelled.cancelled_at = now
        cancelled.save()
        result = agenda(self.ana, now)
        titles = [i["title"] for i in result["today"] + result["later"]]
        self.assertEqual(titles, ["Microscope · Imaging"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(mine.title, "Imaging")

    def test_overdue_step_is_listed_today(self):
        now = MIDWEEK
        entry = NotebookEntry.objects.create(title="Exp", author=self.ana)
        NotebookStep.objects.create(entry=entry, body="Order primers", deadline=now - timedelta(days=1))
        NotebookStep.objects.create(entry=entry, body="Done thing", deadline=now - timedelta(days=1), finished=True)
        result = agenda(self.ana, now)
        self.assertEqual([i["title"] for i in result["today"]], ["Order primers"])
        self.assertTrue(result["today"][0]["overdue"])

    def test_dashboard_renders_the_card(self):
        self.book(self.ana, MIDWEEK + timedelta(minutes=20), title="Run")
        self.client.force_login(self.ana)

        with mock.patch("django.utils.timezone.now", return_value=MIDWEEK):
            page = self.client.get(reverse("notebook_dashboard"))

        self.assertContains(page, "Today and this week")
        self.assertContains(page, "Microscope · Run")

    def test_empty_state(self):
        self.client.force_login(self.bob)
        self.assertContains(self.client.get(reverse("notebook_dashboard")), "Nothing booked or due this week.")
