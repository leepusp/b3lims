import json

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


class ELNMolecularLinkTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eln-molecular-owner",
            password="test-password",
        )
        self.client.force_login(self.user)

        self.entry = NotebookEntry.objects.create(
            title="Primary experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )
        self.second_entry = NotebookEntry.objects.create(
            title="Second experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )
        self.molecule = MolecularSequence.objects.create(
            name="Reusable construct",
            sequence_type="dna",
            topology="linear",
            sequence="ATGCGT",
            description="Registry construct",
            owner=self.user,
        )

    def post_json(self, name, args, payload):
        return self.client.post(
            request_path(name, args),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_existing_molecule_can_link_to_multiple_entries(self):
        for entry in [
            self.entry,
            self.second_entry,
        ]:
            response = self.post_json(
                "notebook_link_molecular_sequence_api",
                [entry.id],
                {"molecule_id": self.molecule.id},
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(
            NotebookMolecularLink.objects.filter(
                molecule=self.molecule
            ).count(),
            2,
        )
        self.molecule.refresh_from_db()
        self.assertIsNone(
            self.molecule.source_entry_id
        )

    def test_search_excludes_record_already_linked(self):
        NotebookMolecularLink.objects.create(
            entry=self.entry,
            molecule=self.molecule,
            linked_by=self.user,
        )

        response = self.client.get(
            request_path(
                "search_molecular_sequences_api"
            ),
            {
                "q": "Reusable",
                "entry_id": self.entry.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"],
            [],
        )

    def test_unlink_preserves_registry_record(self):
        link = NotebookMolecularLink.objects.create(
            entry=self.entry,
            molecule=self.molecule,
            linked_by=self.user,
        )

        response = self.post_json(
            "notebook_unlink_molecular_sequence_api",
            [self.entry.id, link.id],
            {},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            NotebookMolecularLink.objects.filter(
                id=link.id
            ).exists()
        )
        self.assertTrue(
            MolecularSequence.objects.filter(
                id=self.molecule.id
            ).exists()
        )

    def test_created_record_receives_origin_and_link(self):
        response = self.post_json(
            "notebook_create_molecular_sequence_api",
            [self.entry.id],
            {
                "name": "Created from ELN",
                "sequence_type": "dna",
                "topology": "linear",
                "sequence": "ATGC",
                "description": "Created in experiment",
            },
        )

        self.assertEqual(response.status_code, 200)

        molecule = MolecularSequence.objects.get(
            name="Created from ELN"
        )
        self.assertEqual(
            molecule.source_entry,
            self.entry,
        )
        self.assertTrue(
            NotebookMolecularLink.objects.filter(
                entry=self.entry,
                molecule=molecule,
            ).exists()
        )

    def test_notebook_context_uses_explicit_links(self):
        NotebookMolecularLink.objects.create(
            entry=self.entry,
            molecule=self.molecule,
            linked_by=self.user,
        )

        response = self.client.get(
            request_path("notebook_index"),
            {"entry_id": self.entry.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.molecule.name,
        )
        self.assertEqual(
            response.context[
                "experiment_context_counts"
            ]["molecules"],
            1,
        )
