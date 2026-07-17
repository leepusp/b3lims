from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    NotebookEntry,
)


def request_path(name, args=None):
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularWorkspaceFrontendTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="molecular-ui-owner",
            password="test-password",
        )
        self.viewer = get_user_model().objects.create_user(
            username="molecular-ui-viewer",
            password="test-password",
        )
        self.entry = NotebookEntry.objects.create(
            title="Shared molecular notebook",
            author=self.owner,
            visibility="lab",
        )
        self.molecule = MolecularSequence.objects.create(
            name="Validated plasmid",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCGTACGAATTC",
            source_entry=self.entry,
            owner=self.owner,
        )

    def test_owner_receives_clean_editable_workspace(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.molecule.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "internal/lab_tools/molecular_workspace.js",
        )
        self.assertContains(
            response,
            'data-can-edit="true"',
        )
        self.assertNotContains(response, "unpkg.com")
        self.assertNotContains(response, "localStorage")
        self.assertNotContains(response, "buildDemoFeatures")
        self.assertNotContains(response, "SeqViz")

    def test_lab_viewer_receives_read_only_workspace(self):
        self.client.force_login(self.viewer)

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.molecule.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-can-edit="false"',
        )
        self.assertContains(response, "Read only")
        self.assertNotContains(
            response,
            'id="mw-save"',
        )
        self.assertNotContains(
            response,
            'id="mw-delete"',
        )
