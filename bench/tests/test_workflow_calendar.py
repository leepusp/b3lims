import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bench.services import calendar_feed
from core.models.lab_tools.workflow import Workflow


class WorkflowCalendarTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.ana = User.objects.create_user("ana", password="x")
        self.bia = User.objects.create_user("bia", password="x")
        self.client.force_login(self.ana)
        self.workflow = Workflow.objects.create(name="Cloning", owner=self.ana)

    def api(self, payload, user=None):
        if user:
            self.client.force_login(user)

        return self.client.post(
            reverse("workflow_api", args=[self.workflow.pk]), json.dumps(payload), content_type="application/json"
        )

    def add(self, title="Step", **extra):
        return self.api({"action": "add_step", "step": {"title": title, **extra}}).json()["step_id"]

    def feed(self, user):
        start = timezone.now() - timedelta(days=1)

        return calendar_feed.feed(user, start, start + timedelta(days=30), ["workflow"])

    def test_due_steps_show_in_the_calendar_for_the_assignee_or_owner(self):
        due = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        mine = self.add("Mine", due_date=due)
        assigned = self.add("Assigned to Bia", due_date=due, assignee=self.bia.pk)
        finished = self.add("Done already", due_date=due, status="done")

        self.assertEqual({e["id"] for e in self.feed(self.ana)}, {f"workflow:{mine}"})

        self.workflow.members.add(self.bia)

        self.assertEqual({e["id"] for e in self.feed(self.bia)}, {f"workflow:{assigned}"})
        self.assertNotIn(f"workflow:{finished}", {e["id"] for e in self.feed(self.ana)})

    def test_archived_workflows_leave_the_calendar(self):
        due = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")

        self.add("Soon", due_date=due)
        self.api({"action": "update", "status": "archived"})

        self.assertEqual(self.feed(self.ana), [])


