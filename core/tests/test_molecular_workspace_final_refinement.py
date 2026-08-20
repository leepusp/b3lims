from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MolecularWorkspaceFinalRefinementTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        cls.template = (
            base
            / "molecular_sequence_detail.html"
        ).read_text()

        cls.workspace = (
            base
            / "molecular_workspace.js"
        ).read_text()

        cls.workspace_css = (
            base
            / "molecular_workspace.css"
        ).read_text()

        cls.seqviz = (
            base
            / "molecular_seqviz.js"
        ).read_text()

        cls.map_js = (
            base
            / "molecular_plasmid_map.js"
        ).read_text()

        cls.map_css = (
            base
            / "molecular_plasmid_map.css"
        ).read_text()

        cls.linear = (
            base
            / "molecular_linear_browser.js"
        ).read_text()

        cls.linear_css = (
            base
            / "molecular_linear_browser.css"
        ).read_text()

        cls.protein_css = (
            base
            / "molecular_protein_alignment.css"
        ).read_text()

    def test_creation_surfaces(self):
        self.assertNotIn(
            'id="mw-selection-feature"',
            self.template,
        )

        self.assertIn(
            'id="mw-seqviz-create-feature"',
            self.template,
        )

        self.assertIn(
            'id="mw-feature-add"',
            self.template,
        )

    def test_shared_annotation_drawer(self):
        self.assertIn(
            (
                "event.detail?.snapshot"
                "?.selectedFeature"
            ),
            self.workspace,
        )

        self.assertNotIn(
            "event.detail?.selectedFeature",
            self.workspace,
        )

    def test_rna_units(self):
        self.assertIn(
            'return "nt";',
            self.workspace,
        )

        self.assertIn(
            "function selectionUnit()",
            self.seqviz,
        )

        self.assertIn(
            "Nucleotides / row",
            self.linear,
        )

    def test_rna_restrictions(self):
        self.assertGreaterEqual(
            self.workspace.count(
                '["protein", "rna"].includes('
            ),
            2,
        )

        self.assertIn(
            'workspaceSequenceType() === "rna"',
            self.linear,
        )

    def test_rna_detailed_map(self):
        self.assertIn(
            "function isRnaWorkspace()",
            self.map_js,
        )

        self.assertIn(
            "button.hidden = unavailable;",
            self.map_js,
        )

    def test_collision_labels(self):
        self.assertIn(
            "function allocateMapLabelLane(",
            self.workspace,
        )

        self.assertNotIn(
            "index % 3",
            self.workspace,
        )

    def test_density_and_label_styles(self):
        self.assertIn(
            "let base = 0.045;",
            self.map_js,
        )

        self.assertIn(
            "paint-order: stroke fill;",
            self.workspace_css,
        )

        self.assertIn(
            "paint-order: stroke fill;",
            self.map_css,
        )

        self.assertIn(
            "paint-order: stroke fill;",
            self.linear_css,
        )

    def test_protein_responsive_fix_preserved(self):
        """Preserve the responsive Protein contract in Final V1."""

        for marker in (
            "PROTEIN FINAL WORKSPACE V1 20260812",
            ".mw-protein-final-stage",
            ".mw-protein-final-pane",
            ".mpa-alignment-block-scroll",
            ".mpa-alignment-matrix",
            "min-width: 0;",
            "overflow-x: auto;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.protein_css,
                )
