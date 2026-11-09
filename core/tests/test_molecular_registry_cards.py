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

    def test_digest_is_a_window_of_the_viewer_not_a_separate_mode(self):
        html = self._page("plasmid", "circular")
        self.assertIn('data-mwv-layout="digest"', html)
        self.assertNotIn('data-mwb-mode="digest"', html)
        self.assertLess(html.index('id="mw-split"'), html.index('id="mw-digest"'))

        for kind in ("rna", "protein"):
            self.assertNotIn('id="mw-digest"', self._page(kind, "linear"))

    def test_features_and_orfs_are_windows_of_the_viewer(self):
        html = self._page("plasmid", "circular")

        for layout in ("features", "orfs", "digest"):
            self.assertIn('data-mwv-layout="%s"' % layout, html)

        for pane in ("mw-features", "mw-orfs", "mw-digest"):
            self.assertLess(html.index('id="mw-split"'), html.index('id="%s"' % pane))

        self.assertIn("molecular_features_panel.js", html)
        self.assertIn("molecular_orf_panel.js", html)

        for kind in ("rna", "protein"):
            other = self._page(kind, "linear")
            self.assertNotIn('data-mwv-layout="orfs"', other)
            self.assertNotIn('id="mw-orfs"', other)

    def test_rna_and_protein_share_the_map_and_sequence_canvases(self):
        # One layout for every sequence type: map + sequence side by side,
        # the edit strip, and the Features window; only ORFs stay nucleotide-only.
        for kind in ("rna", "protein"):
            html = self._page(kind, "linear")
            self.assertIn('id="mmc"', html)
            self.assertIn('id="msc"', html)
            self.assertIn('id="mw-editstrip"', html)
            self.assertIn('data-mwv-layout="both"', html)
            self.assertIn('data-mwv-layout="features"', html)


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


class ViewerWindowsLayoutWiringTests(TestCase):
    def setUp(self):
        self.tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"

    def test_gel_has_appearance_options_and_png_export(self):
        digest = (self.tools / "molecular_digest.js").read_text()

        for needle in ("THEMES", "ui.bright", "ui.thick", "ui.labels", "downloadGel", "ResizeObserver", "biobank.digest.gellook"):
            self.assertIn(needle, digest)

    def test_orf_window_draws_arrows_and_clusters(self):
        orfs = (self.tools / "molecular_orf_panel.js").read_text()

        for needle in ("function arrow(", "clustersOf", "renderClusters", "mwp-clusterhead"):
            self.assertIn(needle, orfs)

    def test_left_pane_can_be_map_sequence_or_hidden_and_resized(self):
        bench = (self.tools / "molecular_workbench.js").read_text()
        css = (self.tools / "molecular_seq_canvas.css").read_text()

        for needle in ("paneLeft", "mw-divider", "mw-grip", "--mw-left", "biobank.viewer."):
            self.assertIn(needle, bench)

        self.assertIn(".mw-divbtn.is-active", css)
        self.assertIn(".mw-split.is-leftless", css)


class GelPhotoWindowWiringTests(TestCase):
    def setUp(self):
        self.tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"

    def test_gel_photo_reader_has_calibration_detection_and_exports(self):
        gel = (self.tools / "molecular_gel_panel.js").read_text()

        for needle in ("function estimate(", "function detect(", "exportPng", "exportCsv", "window.BiobankGel", "Detect marker"):
            self.assertIn(needle, gel)

    def test_gel_window_is_a_viewer_layout_for_dna_records_only(self):
        from django.template.loader import get_template

        source = get_template("internal/lab_tools/molecular_sequence_detail.html").template.source

        self.assertIn('data-mwv-layout="gel"', source)
        self.assertIn('id="mw-gel"', source)
        self.assertIn("molecular_gel_panel.js", source)
        self.assertIn('gel: "mw-gel"', (self.tools / "molecular_workbench.js").read_text())

    def test_orf_window_includes_orfs_over_the_origin(self):
        orfs = (self.tools / "molecular_orf_panel.js").read_text()

        self.assertIn("wraps", orfs)
        self.assertIn("sequence + sequence", orfs)


class PrimerWindowAndGenbankExportTests(TestCase):
    def setUp(self):
        self.tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"

    def test_primer_window_checks_primers_and_simulates_pcr(self):
        primers = (self.tools / "molecular_primer_panel.js").read_text()

        for needle in ("function findSites(", "function products(", "meltingTemperature", "window.BiobankPrimers", "hairpin", "longestComplement"):
            self.assertIn(needle, primers)

    def test_primer_window_is_wired_for_primer_and_dna_records(self):
        from django.template.loader import get_template

        source = get_template("internal/lab_tools/molecular_sequence_detail.html").template.source

        self.assertIn('data-mwv-layout="primers"', source)
        self.assertIn('id="mw-primers"', source)
        self.assertIn("molecular_primer_panel.js", source)
        self.assertIn('primers: "mw-primers"', (self.tools / "molecular_workbench.js").read_text())

    def test_genbank_export_uses_standard_feature_keys_and_locus_columns(self):
        workspace = (self.tools / "molecular_workspace.js").read_text()

        for needle in ('ori: "rep_origin"', 'primer_bind', '"misc_feature"', "ApEinfo_fwdcolor", "padStart(11)", "mol_type"):
            self.assertIn(needle, workspace)


class MolecularSequenceDataApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.owner = get_user_model().objects.create_user(username="data-api-owner", password="pw")
        self.other = get_user_model().objects.create_user(username="data-api-other", password="pw")

    def make(self):
        from core.models.lab_tools.notebook import MolecularSequence

        return MolecularSequence.objects.create(owner=self.owner, name="DataApi", sequence_type="dna", sequence="ATGCATGC", length=8)

    def test_owner_reads_the_sequence(self):
        from django.test import override_settings
        from django.urls import reverse

        record = self.make()
        self.client.force_login(self.owner)

        with override_settings(FORCE_SCRIPT_NAME=None):
            response = self.client.get(reverse("molecular_sequence_data_api", args=[record.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sequence"], "ATGCATGC")
        self.assertEqual(response.json()["name"], "DataApi")

    def test_other_user_and_anonymous_cannot_read_it(self):
        from django.test import override_settings
        from django.urls import reverse

        record = self.make()

        with override_settings(FORCE_SCRIPT_NAME=None):
            url = reverse("molecular_sequence_data_api", args=[record.id])
            self.assertIn(self.client.get(url).status_code, (302, 401, 403))
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_post_is_refused(self):
        from django.test import override_settings
        from django.urls import reverse

        record = self.make()
        self.client.force_login(self.owner)

        with override_settings(FORCE_SCRIPT_NAME=None):
            self.assertEqual(self.client.post(reverse("molecular_sequence_data_api", args=[record.id])).status_code, 405)


class CloningWindowWiringTests(TestCase):
    def test_cloning_window_is_wired_with_restriction_and_homology_plans(self):
        from django.template.loader import get_template

        tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"
        cloning = (tools / "molecular_cloning_panel.js").read_text()
        source = get_template("internal/lab_tools/molecular_sequence_detail.html").template.source

        for needle in ("function restrictionPlan(", "function homologyPlan(", "replaceRange", "window.BiobankCloning"):
            self.assertIn(needle, cloning)

        self.assertIn('data-mwv-layout="cloning"', source)
        self.assertIn('id="mw-cloning"', source)
        self.assertIn("molecular_cloning_panel.js", source)
        self.assertIn('cloning: "mw-cloning"', (tools / "molecular_workbench.js").read_text())


class SaveCopyAsNewRecordWiringTests(TestCase):
    def test_workspace_can_save_what_is_on_screen_as_a_new_record(self):
        from django.template.loader import get_template

        tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"
        workspace = (tools / "molecular_workspace.js").read_text()
        source = get_template("internal/lab_tools/molecular_sequence_detail.html").template.source

        self.assertIn("async function saveAsNewRecord(", workspace)
        self.assertIn("saveAsNewRecord,", workspace)
        self.assertIn('"save-copy"', (tools / "molecular_workbench.js").read_text())
        self.assertIn('data-mwv-act="save-copy"', source)
        self.assertIn("data-registry-url", source)


class ViewerWindowManagerTests(TestCase):
    def render(self, record_type):
        from django.contrib.auth import get_user_model
        from django.test import override_settings
        from django.urls import reverse

        from core.models.lab_tools.notebook import MolecularSequence

        user = get_user_model().objects.create_user(username="wm-" + record_type, password="pw")
        record = MolecularSequence.objects.create(
            owner=user, name="WM " + record_type, sequence_type=record_type, topology="linear", sequence="ATGCATGCATGC", length=12,
        )
        self.client.force_login(user)

        with override_settings(FORCE_SCRIPT_NAME=None):
            return self.client.get(reverse("molecular_sequence_detail", args=[record.id])).content.decode()

    def test_plasmid_gets_every_window_that_can_be_opened_or_closed(self):
        html = self.render("plasmid")

        for name in ("features", "orfs", "digest", "cloning", "gel", "primers"):
            self.assertIn(f'data-mwv-window="{name}"', html)

    def test_primer_has_its_own_view_without_map_orfs_or_digest(self):
        html = self.render("primer")

        self.assertIn('data-mwv-window="primers"', html)
        self.assertIn("data-mwv-fixed", html)

        for name in ("map", "both", "orfs", "digest", "cloning", "gel", "features"):
            self.assertNotIn(f'data-mwv-layout="{name}"', html)

    def test_protein_and_rna_do_not_get_dna_windows(self):
        for record_type in ("protein", "rna"):
            html = self.render(record_type)

            for name in ("digest", "cloning", "gel", "primers"):
                self.assertNotIn(f'data-mwv-window="{name}"', html)

    def test_window_manager_code_is_present(self):
        tools = Path(__file__).resolve().parents[1] / "static/internal/lab_tools"
        bench = (tools / "molecular_workbench.js").read_text()

        for needle in ("DEFAULT_OPEN", "openWindow", "closeWindow", "biobank.windows.", "window.BiobankWindows"):
            self.assertIn(needle, bench)
