from pathlib import Path

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


class MapCanvasMountTests(TestCase):
    def _page(self, sequence_type, topology):
        user = get_user_model().objects.create_user(
            f"canvas-{sequence_type}", password="x"
        )
        molecule = MolecularSequence.objects.create(
            name="m", sequence_type=sequence_type, topology=topology,
            sequence="ATGC" * 10 if sequence_type != "protein" else "MKTAYIAK",
            owner=user,
        )
        self.client.force_login(user)

        return self.client.get(
            reverse("molecular_sequence_detail", args=[molecule.id])
        ).content.decode()

    def test_nucleotide_records_get_the_interactive_map(self):
        for kind, topology in (("plasmid", "circular"), ("dna", "linear"), ("insert", "linear")):
            html = self._page(kind, topology)
            self.assertIn('id="mmc"', html)
            self.assertIn("molecular_map_canvas.js", html)

    def test_nucleotide_records_get_the_sequence_editor(self):
        for kind, topology in (("plasmid", "circular"), ("dna", "linear"), ("insert", "linear")):
            html = self._page(kind, topology)
            self.assertIn('id="msc"', html)
            self.assertIn("molecular_seq_canvas.js", html)
            self.assertIn("molecular_seq_canvas.css", html)

    def test_nucleotide_records_do_not_expose_the_old_viewers(self):
        html = self._page("plasmid", "circular")
        self.assertIn("mw-canvas-record", html)
        self.assertNotIn("Edit sequence text", html)
        self.assertIn('id="mw-editstrip"', html)
        self.assertIn("molecular_edit_strip.js", html)
        self.assertIn('class="mwv-more mwv-view" hidden', html)

        workbench = (
            Path(__file__).resolve().parents[1]
            / "static/internal/lab_tools/molecular_workbench.js"
        ).read_text()
        self.assertNotIn("classic map", workbench)

    def test_annotations_can_be_dragged_on_the_map_and_in_the_sequence(self):
        tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"

        for name in ("molecular_workspace.js", "molecular_map_canvas.js", "molecular_seq_canvas.js"):
            self.assertIn("editFeature", (tools / name).read_text(), name)

        self.assertIn('"feature-edit"', (tools / "molecular_map_canvas.js").read_text())

    def test_rna_and_protein_keep_their_own_views(self):
        for kind in ("rna", "protein"):
            html = self._page(kind, "linear")
            self.assertNotIn('id="mmc"', html)
            self.assertNotIn('id="msc"', html)


class DigestPanelWiringTests(TestCase):
    def test_digest_panel_cuts_and_image_export_are_wired(self):
        tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"
        digest = (tools / "molecular_digest.js").read_text()
        seq = (tools / "molecular_seq_canvas.js").read_text()
        maps = (tools / "molecular_map_canvas.js").read_text()

        self.assertIn("biobank:digest-change", digest)
        self.assertIn("window.BiobankDigest", digest)
        self.assertIn("BiobankDigest", seq)
        self.assertIn("drawCircularCuts", maps)
        self.assertIn("downloadImage", maps)
        self.assertNotIn("renderDigest", (tools / "molecular_workbench.js").read_text())
