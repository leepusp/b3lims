import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC = Path(settings.BASE_DIR, "core/static/internal/lab_tools")
TEMPLATE = Path(
    settings.BASE_DIR,
    "core/interfaces/internal/lab_tools/molecular_sequence_detail.html",
)


class MolecularProLayerTests(SimpleTestCase):
    def read(self, name):
        return (STATIC / name).read_text(encoding="utf-8")

    def test_assets_are_wired_for_rna_and_protein_only(self):
        template = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("molecular_pro.css", template)
        self.assertIn("molecular_rna_pro.js", template)
        self.assertIn("molecular_alignment_pro.js", template)
        # The shared stylesheet is gated to the two types that use it.
        gate = template.index("molecular_pro.css")
        self.assertIn(
            'sequence_type == "rna" or molecule.sequence_type == "protein"',
            template[gate - 200:gate],
        )

    def test_modules_have_valid_syntax(self):
        node = shutil.which("node")

        if not node:
            self.skipTest("node is not installed")

        for name in ("molecular_rna_pro.js", "molecular_alignment_pro.js"):
            result = subprocess.run(
                [node, "--check", str(STATIC / name)],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_workspace_events_are_listened_on_the_root(self):
        # The event is dispatched on #molecular-workspace and does not
        # bubble, so listening on window would never fire.
        for name in ("molecular_rna_pro.js", "molecular_alignment_pro.js"):
            source = self.read(name)

            self.assertIn(
                'root.addEventListener("biobank:molecular-workspace-change"',
                source,
            )
            self.assertNotIn(
                'window.addEventListener("biobank:molecular-workspace-change"',
                source,
            )

    def test_palette_control_is_not_nested_in_the_find_label(self):
        source = self.read("molecular_protein_alignment.js")

        self.assertIn('search.closest("label")', source)
        self.assertIn("host.parentElement.insertBefore", source)

    def test_workbench_exposes_the_mode_to_css(self):
        self.assertIn(
            "root.dataset.mwbMode = mode;",
            self.read("molecular_workbench.js"),
        )
        self.assertIn('[data-mwb-mode="structure"]', self.read("molecular_pro.css"))

    def test_rna_layer_offers_views_stats_compare_and_export(self):
        source = self.read("molecular_rna_pro.js")

        for needle in ("Arc", "Circle", "Dot-bracket", "Pairs", "Compare with",
                       "CT file", "Pairs CSV", "Pseudoknot", "Multiloops"):
            self.assertIn(needle, source)

    def test_alignment_layer_offers_schemes_search_and_export(self):
        source = self.read("molecular_alignment_pro.js")

        for needle in ("Identity to reference", "Hydrophobicity", "Conservation",
                       "Consensus FASTA", "Go to position", "Motif (regex)"):
            self.assertIn(needle, source)


class MolecularProLoopGuardTests(SimpleTestCase):
    """A layer that observes the DOM must never re-trigger itself.

    Regression: calling classList.remove() on an element without the class
    still rewrites the attribute, which an attribute observer sees again. On a
    protein without alignments this froze the page.
    """

    def test_alignment_layer_only_touches_dom_when_needed(self):
        source = (STATIC / "molecular_alignment_pro.js").read_text(encoding="utf-8")

        self.assertIn('if (proRoot || shell.classList.contains("is-pro"))', source)

    def test_observers_are_debounced(self):
        for name in ("molecular_alignment_pro.js", "molecular_rna_pro.js"):
            source = (STATIC / name).read_text(encoding="utf-8")

            self.assertIn("queued", source, name)
            self.assertIn("setTimeout", source, name)


class MolecularUnifiedLayoutTests(SimpleTestCase):
    """RNA/Protein use one layout; interactive 2D/3D structure; no topology field."""

    def test_layout_module_is_loaded_before_the_rna_layer(self):
        template = TEMPLATE.read_text(encoding="utf-8")

        self.assertLess(
            template.index("molecular_rna_layout.js"),
            template.index("molecular_rna_pro.js"),
        )

    def test_layout_unit_tests_run_with_node(self):
        node = shutil.which("node")

        if not node:
            self.skipTest("node is not installed")

        script = Path(settings.BASE_DIR, "core/tests/js/test_rna_layout.cjs")
        result = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rna layout ok", result.stdout)

    def test_rna_layer_offers_2d_3d_and_pair_editing(self):
        source = (STATIC / "molecular_rna_pro.js").read_text(encoding="utf-8")

        for token in ('["2d", "Structure"]', '["3d", "3D"]', "Edit pairs", "Save as new structure", "build3d"):
            self.assertIn(token, source)

    def test_map_and_sequence_layout_is_shared_and_modes_are_hidden(self):
        css = (STATIC / "molecular_pro.css").read_text(encoding="utf-8")
        template = TEMPLATE.read_text(encoding="utf-8")

        # The Map|Structure mode buttons are gone for RNA and Protein...
        self.assertIn('.mw-page[data-sequence-type="rna"] .mwb-modes', css)
        # ...while the working layout switch (map + sequence / map / sequence) stays.
        self.assertNotIn('.mwv-seg{display', css.replace(" ", ""))
        self.assertIn('data-mwv-layout="both"', template)
        self.assertIn("mw-canvas-record", template)

    def test_protein_alignment_can_select_trim_and_annotate_columns(self):
        source = (STATIC / "molecular_alignment_pro.js").read_text(encoding="utf-8")

        for token in ("Trim to selection", "Add annotation", "Select in protein", "Export selection", "Restore full alignment"):
            self.assertIn(token, source)

    def test_topology_is_not_asked_when_creating_a_record(self):
        registry = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/molecular_registry.html",
        ).read_text(encoding="utf-8")
        start = registry.index('for="molecule-topology"')
        block = registry[max(0, start - 200):start]

        self.assertIn("hidden", block)


class MolecularStructureWindowTests(SimpleTestCase):
    """Structure is a window of the viewer, next to the map or the sequence."""

    def test_structure_is_a_viewer_window_for_rna_and_protein(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        workbench = (STATIC / "molecular_workbench.js").read_text(encoding="utf-8")
        window = (STATIC / "molecular_structure_window.js").read_text(encoding="utf-8")

        self.assertIn('data-mwv-layout="structure"', template)
        self.assertIn('id="mw-structure"', template)
        self.assertLess(template.index('id="mw-split"'), template.index('id="mw-structure"'))
        self.assertIn('structure: "mw-structure"', workbench)
        self.assertIn("mw-rna-secondary-structure", window)
        self.assertIn("mw-protein-structure", window)

    def test_window_script_is_loaded_and_valid(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        node = shutil.which("node")

        self.assertIn("molecular_structure_window.js", template)

        if node:
            result = subprocess.run(
                [node, "--check", str(STATIC / "molecular_structure_window.js")],
                capture_output=True, text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)


class RegistryHomeLayoutTests(SimpleTestCase):
    def test_home_has_no_coming_soon_card_and_uses_the_full_width(self):
        registry = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/molecular_registry.html",
        ).read_text(encoding="utf-8")
        css = Path(STATIC, "molecular_registry_hub.css").read_text(encoding="utf-8")

        self.assertNotIn("Coming to the Registry", registry)
        self.assertIn(".mr-home{display:flex;flex-direction:column", css)


class RnaRealStructureWiringTests(SimpleTestCase):
    def test_rna_page_loads_molstar_and_the_3d_module(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        pro = (STATIC / "molecular_rna_pro.js").read_text(encoding="utf-8")

        self.assertIn("molecular_rna_structure3d.js", template)
        self.assertIn("BiobankRnaStructure3D", pro)
        self.assertIn("draw3dReal", pro)
        self.assertEqual(template.count("molstar-5.11.0.css"), 2)

        node = shutil.which("node")

        if node:
            result = subprocess.run(
                [node, "--check", str(STATIC / "molecular_rna_structure3d.js")],
                capture_output=True, text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)


class SequenceColorStandardTests(SimpleTestCase):
    def test_all_types_share_one_colour_control_and_palette_style(self):
        canvas = (STATIC / "molecular_seq_canvas.js").read_text(encoding="utf-8")

        self.assertIn("RESIDUE_COLOR", canvas)
        self.assertIn("showColors", canvas)
        self.assertIn('" Colors"', canvas)
        # DNA/RNA bases and amino-acid classes use the same hues.
        for hue in ("#2B8A3E", "#C92A2A", "#E67700", "#1971C2"):
            self.assertGreaterEqual(canvas.count(hue), 2, hue)
        self.assertIn('s.sequenceType === "protein" ? RESIDUE_COLOR : BASE_COLOR', canvas)
