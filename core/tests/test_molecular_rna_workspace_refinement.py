from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MolecularRnaWorkspaceRefinementTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        cls.template = (
            base / "molecular_sequence_detail.html"
        ).read_text(encoding="utf-8")

        cls.workspace = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js'
        ).read_text(encoding="utf-8")

        cls.workspace_css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.css'
        ).read_text(encoding="utf-8")

        cls.seqviz = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_seqviz.js'
        ).read_text(encoding="utf-8")

        cls.rna = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_rna_secondary_structure.js'
        ).read_text(encoding="utf-8")

        cls.rna_css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_rna_secondary_structure.css'
        ).read_text(encoding="utf-8")

    def test_secondary_structure_is_main_view(self):
        self.assertEqual(
            self.template.count(
                'data-mw-view="secondary-structure"'
            ),
            1,
        )
        self.assertEqual(
            self.template.count(
                'data-mw-view-panel="secondary-structure"'
            ),
            1,
        )
        self.assertIn(
            "Secondary structure",
            self.template,
        )
        self.assertIn(
            '"secondary-structure",',
            self.workspace,
        )

    def test_secondary_structure_reuses_workspace_panel(self):
        self.assertIn(
            'document.getElementById(\n'
            '                "mw-rna-secondary-structure"',
            self.rna,
        )
        self.assertIn(
            "card.replaceChildren();",
            self.rna,
        )
        self.assertNotIn(
            'const card = createElement(\n'
            '            "section",\n'
            '            "mw-card mrss-card",',
            self.rna,
        )
        self.assertNotIn(
            'sequenceCard.insertAdjacentElement(',
            self.rna,
        )

    def test_secondary_structure_gets_main_panel_space(self):
        self.assertIn(
            '[data-mw-view-panel="secondary-structure"]',
            self.workspace_css,
        )
        self.assertIn(
            ".mw-rna-secondary-view .mrss-forna-mount",
            self.rna_css,
        )
        self.assertIn(
            "min-height: 520px;",
            self.rna_css,
        )

    def test_forna_is_activated_by_main_view(self):
        self.assertIn(
            "activateSecondaryStructureView",
            self.rna,
        )
        self.assertIn(
            'event.detail?.view\n'
            '                    === "secondary-structure"',
            self.rna,
        )
        self.assertIn(
            'root.dataset.workspaceView\n'
            '            === "secondary-structure"',
            self.rna,
        )
        self.assertIn(
            "await loadStructures();",
            self.rna,
        )

    def test_linear_rna_uses_linear_seqviz(self):
        self.assertIn(
            'data.sequenceType === "rna"',
            self.seqviz,
        )
        self.assertIn(
            'data.topology === "linear"',
            self.seqviz,
        )
        self.assertIn(
            '? "linear"',
            self.seqviz,
        )

    def test_rna_restriction_controls_are_suppressed(self):
        self.assertIn(
            'const isRnaWorkspace = (',
            self.seqviz,
        )
        self.assertIn(
            "enzymeControl.hidden = true;",
            self.seqviz,
        )
        self.assertIn(
            'enzymeMode.value = "none";',
            self.seqviz,
        )
        self.assertIn(
            'data.sequenceType === "rna"',
            self.seqviz,
        )
        self.assertIn(
            "? []",
            self.seqviz,
        )

    def test_rna_complement_control_is_suppressed(self):
        self.assertIn(
            "complementControl.hidden = true;",
            self.seqviz,
        )
        self.assertIn(
            "showComplement.checked = false;",
            self.seqviz,
        )
        self.assertIn(
            'data.sequenceType !== "rna"',
            self.seqviz,
        )

    def test_existing_structure_actions_are_preserved(self):
        for marker in (
            "Add structure",
            "Remove structure",
            "Save structure",
            "Copy source",
            "loadStructures",
            "openStructure",
            "saveStructure",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.rna,
                )

    def test_no_prediction_runtime_is_added(self):
        forbidden = (
            "rnafold.wasm",
            "ViennaRNA",
            "RNAcanvas",
            "predictSecondaryStructure(",
            "automaticPrediction(",
        )

        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(
                    marker,
                    self.rna,
                )
