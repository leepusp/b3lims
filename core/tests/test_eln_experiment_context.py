from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    JupyterNotebook,
    NotebookEntry,
    NotebookKernelDocument,
)


def request_path(name, args=None):
    return reverse(
        name,
        args=args,
    ).removeprefix("/biobank")


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
        self.assertContains(response, "Jupyter analysis")
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

    def test_integrated_jupyter_entry_remains_in_eln(self):
        document = NotebookKernelDocument.objects.create(
            entry=self.entry,
            title="Integrated analysis",
            notebook_json={},
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={self.entry.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self.entry,
            list(response.context["entries"]),
        )
        self.assertEqual(
            response.context["eln_jupyter_document"],
            document,
        )
        self.assertEqual(
            response.context[
                "experiment_context_counts"
            ]["jupyter"],
            1,
        )
        self.assertContains(
            response,
            "Continue analysis",
        )

    def test_migrated_legacy_jupyter_entry_stays_hidden(self):
        legacy_entry = NotebookEntry.objects.create(
            title="Legacy Jupyter-only entry",
            author=self.owner,
            entry_type="analysis",
            visibility="private",
        )
        legacy_document = (
            NotebookKernelDocument.objects.create(
                entry=legacy_entry,
                title="Legacy analysis",
                notebook_json={},
                created_by=self.owner,
                updated_by=self.owner,
            )
        )
        JupyterNotebook.objects.create(
            title="Imported independent notebook",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json={},
            legacy_document=legacy_document,
        )

        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={self.entry.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            legacy_entry,
            list(response.context["entries"]),
        )
