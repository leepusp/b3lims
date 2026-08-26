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

    def test_context_summarizes_linked_record_types(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={self.entry.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Experiment context")
        self.assertContains(response, "Linked samples")
        self.assertContains(response, "Linked reagents")
        self.assertContains(response, "Molecular records")
        self.assertContains(response, "Files and results")
        self.assertContains(response, "Jupyter notebooks")
        self.assertNotContains(response, "Relevant items")

        counts = response.context[
            "experiment_context_counts"
        ]

        self.assertEqual(
            counts,
            {
                "samples": 0,
                "chemicals": 0,
                "molecules": 0,
                "attachments": 0,
                "jupyter": 0,
            },
        )
