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
