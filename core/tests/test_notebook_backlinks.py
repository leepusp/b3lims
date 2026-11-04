"""LIMS entities show the ELN entries that cite them (visible ones only)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Chemical, Sample
from core.models.lab_tools.notebook import (
    NotebookChemicalLink,
    JupyterNotebook,
    MolecularSequence,
    NotebookEntry,
    NotebookJupyterLink,
    NotebookMolecularLink,
    NotebookSampleLink,
)
from core.services import notebook_backlinks as bl


class BacklinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ana = User.objects.create_user(username="bl-ana", password="x")
        cls.bob = User.objects.create_user(username="bl-bob", password="x")
        cls.shared = NotebookEntry.objects.create(
            title="Lab-wide gel", author=cls.ana, visibility="lab"
        )
        cls.private = NotebookEntry.objects.create(
            title="Secret idea", author=cls.ana, visibility="private"
        )
        cls.sample = Sample.objects.create(
            sample_id="BL-001", sample_type="Other", owner=cls.ana, is_active=True
        )
        cls.chemical = Chemical.objects.create(
            name="Agarose", quantity="1 kg", quantity_value="1", quantity_unit="kg",
            created_by=cls.ana,
        )
        cls.molecule = MolecularSequence.objects.create(
            name="pTest", sequence_type="dna", topology="linear",
            sequence="ATGC", owner=cls.ana, source_entry=cls.private,
        )
        cls.notebook = JupyterNotebook.objects.create(
            title="Analysis", owner=cls.ana, updated_by=cls.ana,
            notebook_json={"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5},
        )

    def test_sample_links_and_mentions_respect_visibility(self):
        NotebookSampleLink.objects.create(entry=self.shared, sample=self.sample, linked_by=self.ana)
        NotebookSampleLink.objects.create(entry=self.private, sample=self.sample, linked_by=self.ana)
        self.private.mentions.add(self.sample)
        self.shared.mentions.add(self.sample)
        mine = bl.entries_for_sample(self.ana, self.sample)
        theirs = bl.entries_for_sample(self.bob, self.sample)
        self.assertEqual({i["entry"] for i in mine}, {self.shared, self.private})
        self.assertEqual([i["entry"] for i in theirs], [self.shared])
        self.assertEqual(theirs[0]["via"], "linked, mentioned")  # merged, listed once

    def test_chemical_and_jupyter(self):
        NotebookChemicalLink.objects.create(entry=self.shared, chemical=self.chemical, linked_by=self.ana)
        NotebookJupyterLink.objects.create(entry=self.shared, notebook=self.notebook, linked_by=self.ana)
        self.assertEqual([i["entry"] for i in bl.entries_for_chemical(self.bob, self.chemical)], [self.shared])
        self.assertEqual([i["entry"] for i in bl.entries_for_jupyter(self.bob, self.notebook)], [self.shared])

    def test_molecule_creation_entry_hidden_when_private(self):
        NotebookMolecularLink.objects.create(entry=self.shared, molecule=self.molecule, linked_by=self.ana)
        self.assertEqual({i["entry"] for i in bl.entries_for_molecule(self.ana, self.molecule)},
                         {self.shared, self.private})
        self.assertEqual([i["entry"] for i in bl.entries_for_molecule(self.bob, self.molecule)], [self.shared])

    def test_trashed_entries_are_not_listed(self):
        from django.utils import timezone
        NotebookChemicalLink.objects.create(entry=self.shared, chemical=self.chemical, linked_by=self.ana)
        NotebookEntry.objects.filter(pk=self.shared.pk).update(deleted_at=timezone.now())
        self.assertEqual(bl.entries_for_chemical(self.ana, self.chemical), [])

    def test_chemical_page_shows_the_panel(self):
        NotebookChemicalLink.objects.create(entry=self.shared, chemical=self.chemical, linked_by=self.ana)
        self.client.force_login(self.ana)
        html = self.client.get(reverse("chemical_detail", args=[self.chemical.pk])).content.decode()
        self.assertIn("Used in experiments", html)
        self.assertIn("Lab-wide gel", html)
        self.assertIn(reverse("notebook_entry", args=[self.shared.pk]), html)

    def _panel(self, url_name, obj_pk, expect):
        self.client.force_login(self.ana)
        response = self.client.get(reverse(url_name, args=[obj_pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Used in experiments", html)
        self.assertIn(expect, html)

    def test_sample_page_shows_the_panel(self):
        NotebookSampleLink.objects.create(entry=self.shared, sample=self.sample, linked_by=self.ana)
        self._panel("sample_detail", self.sample.pk, "Lab-wide gel")

    def test_molecule_page_shows_the_panel(self):
        NotebookMolecularLink.objects.create(entry=self.shared, molecule=self.molecule, linked_by=self.ana)
        self._panel("molecular_sequence_detail", self.molecule.pk, "Lab-wide gel")

    def test_jupyter_page_shows_the_panel(self):
        NotebookJupyterLink.objects.create(entry=self.shared, notebook=self.notebook, linked_by=self.ana)
        self._panel("jupyter_workspace", self.notebook.pk, "Lab-wide gel")
