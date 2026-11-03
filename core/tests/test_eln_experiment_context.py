from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    NotebookEntry,
)


def request_path(name, args=None):
    return reverse(
        name,
        args=args,
    )


@override_settings(FORCE_SCRIPT_NAME=None)
class ElnExperimentContextTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="eln-context-owner",
            password="test-password",
        )
        self.entry = NotebookEntry.objects.create(
            title="Context experiment",
            author=self.owner,
            entry_type="experiment",
            visibility="private",
        )

    def test_context_requires_authentication(self):
        response = self.client.get(
            request_path("notebook_index")
        )

        self.assertEqual(response.status_code, 302)

