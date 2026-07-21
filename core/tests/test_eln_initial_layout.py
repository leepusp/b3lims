from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import (
    NotebookEntry,
)


def request_path(name, args=None):
    path = reverse(name, args=args)
    script_name = settings.FORCE_SCRIPT_NAME or ""

    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"

    return path


class ELNInitialLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eln-initial-layout",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_initial_state_hides_linked_context_sidebar(self):
        response = self.client.get(
            request_path("notebook_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "notebook-shell-empty",
        )
        self.assertNotContains(
            response,
            'id="linked-experiment-context"',
        )
        self.assertNotContains(
            response,
            'notebook-panel-header">Linked samples',
        )
        self.assertNotContains(
            response,
            'id="sample-search"',
        )
        self.assertNotContains(
            response,
            'id="chemical-search"',
        )

    def test_active_entry_restores_linked_context_sidebar(self):
        entry = NotebookEntry.objects.create(
            title="Active experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )

        response = self.client.get(
            request_path("notebook_index"),
            {"entry_id": entry.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            (
                'class="notebook-shell '
                'notebook-shell-empty"'
            ),
        )
        self.assertContains(
            response,
            'id="linked-experiment-context"',
        )
        self.assertContains(
            response,
            'notebook-panel-header">Linked samples',
        )
        self.assertContains(
            response,
            'id="sample-search"',
        )
        self.assertContains(
            response,
            'id="chemical-search"',
        )
