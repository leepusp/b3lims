from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    NotebookEntry,
    NotebookMolecularLink,
)


def request_path(name, args=None):
    path = reverse(name, args=args)
    script_name = settings.FORCE_SCRIPT_NAME or ""

    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"

    return path


class ELNMolecularLinksFrontendTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eln-molecular-frontend",
            password="test-password",
        )
        self.entry = NotebookEntry.objects.create(
            title="Expandable molecular experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )
        self.molecule = MolecularSequence.objects.create(
            name="Expandable construct",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCGT",
            description="Reusable construct description",
            owner=self.user,
        )
        self.link = NotebookMolecularLink.objects.create(
            entry=self.entry,
            molecule=self.molecule,
            linked_by=self.user,
        )
        self.client.force_login(self.user)

    def notebook_response(self):
        return self.client.get(
            request_path("notebook_index"),
            {
                "entry_id": self.entry.id,
                "tab": "items",
            },
        )

    def test_attachment_tools_are_collapsed_and_searchable(self):
        response = self.notebook_response()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="molecular-record-tools"',
        )
        self.assertContains(
            response,
            'class="collapse mb-3"',
        )
        self.assertContains(
            response,
            "Add molecular record",
        )
        self.assertContains(
            response,
            "Link existing",
        )
        self.assertContains(
            response,
            "New record",
        )
        self.assertContains(
            response,
            'id="molecular-record-search"',
        )
        self.assertContains(
            response,
            reverse("search_molecular_sequences_api"),
        )

    def test_linked_record_is_expandable_and_actionable(self):
        response = self.notebook_response()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.molecule.name,
        )
        self.assertContains(
            response,
            f'id="molecular-link-card-{self.link.id}"',
        )
        self.assertContains(
            response,
            f'id="molecular-link-details-{self.link.id}"',
        )
        self.assertContains(
            response,
            "Insert into notes",
        )
        self.assertContains(
            response,
            "Detach",
        )
        self.assertContains(
            response,
            "Reusable construct description",
        )

    def test_template_exposes_reusable_link_javascript(self):
        template = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "notebook.html",
        ).read_text()

        required_markers = [
            "{% for link in linked_molecular_links %}",
            "function searchMolecularRecords()",
            "function linkMolecularRecord(moleculeId, button)",
            "function unlinkMolecularRecord(linkId, moleculeName)",
            "function insertMolecularRecordIntoNotes(button)",
            "insertRelevantItemIntoMainNote(item)",
            "molecular-record-search-results",
            "data-molecular-link-card",
            "data-molecular-link-details",
        ]

        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, template)

        self.assertNotIn(
            "{% for molecule in molecular_sequences %}",
            template,
        )
