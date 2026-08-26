from pathlib import Path

from django.test import SimpleTestCase


BASE = (
    Path(__file__)
    .resolve()
    .parents[1]
    / "interfaces"
    / "internal"
    / "lab_tools"
)


class MolecularProteinResponsiveLayoutTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_alignment.css'
        ).read_text(
            encoding="utf-8"
        )

        cls.workspace_js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js'
        ).read_text(
            encoding="utf-8"
        )

    def test_final_workspace_uses_available_width(
        self,
    ):
        for marker in (
            ".mw-protein-final-stage",
            ".mw-protein-final-pane",
            "width: 100%;",
            "min-width: 0;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.css,
                )

    def test_alignment_overflow_is_local_to_sequence_blocks(
        self,
    ):
        self.assertIn(
            ".mpa-alignment-block-scroll",
            self.css,
        )

        self.assertIn(
            "overflow-x: auto;",
            self.css,
        )

        self.assertIn(
            ".mpa-alignment-matrix",
            self.css,
        )

    def test_base_alignment_layout_is_preserved(
        self,
    ):
        for marker in (
            ".mpa-body",
            ".mpa-sidebar",
            ".mpa-list",
            ".mpa-metadata",
            ".mpa-toolbar",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.css,
                )

    def test_restriction_track_is_disabled_for_protein_and_rna(
        self,
    ):
        self.assertIn(
            '["protein", "rna"].includes(',
            self.workspace_js,
        )

    def test_protein_density_uses_measured_track_geometry(
        self,
    ):
        start_marker = (
            "        function responsivePreviewBasesPerRow() {"
        )

        end_marker = (
            "\n        function initializeResponsiveSequencePreview()"
        )

        start = self.workspace_js.index(
            start_marker
        )

        end = self.workspace_js.index(
            end_marker,
            start,
        )

        function_source = self.workspace_js[
            start:end
        ]

        for marker in (
            "PROTEIN TRACK GEOMETRY V2 20260813",
            "const measuredPreviewWidth = Number(",
            'currentType() === "protein"',
            'probe.className = "mw-seq-row";',
            '"--mw-row-bases",',
            "base.getBoundingClientRect()",
            "baseRect.width",
            "rowStyle.columnGap",
            "const availableTrackWidth = Math.max(",
            "const sequenceLength = String(",
            r'.replace(/\s+/g, "")',
            "const densityCap = Math.max(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    function_source,
                )

        self.assertNotIn(
            "? 9",
            function_source,
        )

        self.assertIn(
            "180,",
            function_source,
        )

    def test_protein_shell_removes_legacy_inspector_column(
        self,
    ):
        for marker in (
            "PROTEIN FULL-WIDTH SHELL V2 20260813",
            "grid-template-columns: minmax(0, 1fr);",
            ".mw-seqviz-viewer,",
            ".mw-seqviz-inspector {",
            "display: none !important;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.css,
                )
