from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import MolecularFeature, MolecularSequence
from core.services.molecular_registry_cards import (
    melting_temperature,
    protein_mass_kda,
    protein_pi,
)


class CardMathTests(TestCase):
    def test_wallace_tm_for_short_primer(self):
        self.assertEqual(melting_temperature("ATGCATGCAT"), 2 * 6 + 4 * 4)

    def test_protein_mass_and_pi_are_plausible(self):
        seq = "GIVEQCCTSICSLYQLENYCN" + "FVNQHLCGSHLVEALYLVCGERGFFYTPKT"
        self.assertAlmostEqual(protein_mass_kda(seq), 5.8, delta=0.2)
        self.assertGreater(protein_pi(seq), 4.5)
        self.assertLess(protein_pi(seq), 6.5)


class RegistryCardsTests(TestCase):
    def test_home_shows_cards_with_previews(self):
        user = get_user_model().objects.create_user("cards", password="x")
        plasmid = MolecularSequence.objects.create(
            name="pCARD", sequence_type="plasmid", topology="circular",
            sequence="ATGC" * 100, owner=user,
        )
        MolecularFeature.objects.create(
            molecule=plasmid, name="f", start=10, end=80, color="#ff0000"
        )
        MolecularSequence.objects.create(
            name="PRIM", sequence_type="primer", topology="linear",
            sequence="ATGGCTAGCAAAGGAGAAGAAC", owner=user,
        )
        self.client.force_login(user)
        html = self.client.get(reverse("molecular_registry_index")).content.decode()

        self.assertIn("mr-card", html)
        self.assertIn('stroke="#ff0000"', html)
        self.assertIn("<mark>AGAAC</mark>", html)


class CleanRecordNameTests(TestCase):
    def test_uniprot_header_becomes_entry_name(self):
        from core.services.molecular_sequences import clean_record_name

        self.assertEqual(
            clean_record_name(">sp|P01308|INS_HUMAN Insulin OS=Homo sapiens"),
            "INS_HUMAN",
        )

    def test_plain_names_are_untouched(self):
        from core.services.molecular_sequences import clean_record_name

        self.assertEqual(clean_record_name("  pET-28a(+) "), "pET-28a(+)")
        self.assertEqual(clean_record_name(">simple desc"), "simple")
        self.assertEqual(clean_record_name(">"), "")
