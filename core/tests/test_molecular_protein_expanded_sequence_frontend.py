from pathlib import Path

from django.test import SimpleTestCase


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

BASE = (
    ROOT
    / "core/interfaces/internal/lab_tools"
)

DETAIL = (
    BASE
    / "molecular_sequence_detail.html"
)

SPLITTER_JS = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_splitter.js'
)

SPLITTER_CSS = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_splitter.css'
)


class ProteinExpandedSequenceFrontendTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(
        cls,
    ):
        super().setUpClass()

        cls.detail = DETAIL.read_text(
            encoding="utf-8"
        )

        cls.js = SPLITTER_JS.read_text(
            encoding="utf-8"
        )

        cls.css = SPLITTER_CSS.read_text(
            encoding="utf-8"
        )

    def test_existing_javascript_controls_expanded_state(
        self,
    ):
        self.assertIn(
            "syncMolstarExpandedState",
            self.js,
        )

        self.assertIn(
            "is-molstar-expanded",
            self.js,
        )

        self.assertIn(
            "expandToFullscreen",
            self.js,
        )

        self.assertIn(
            "msp-layout-expanded",
            self.js,
        )

        self.assertIn(
            "fullscreenchange",
            self.js,
        )

    def test_expanded_guard_hides_sequence_and_splitter(
        self,
    ):
        marker = (
            "MOLSTAR EXPANDED/FULLSCREEN "
            "EXTERNAL PANEL GUARD V3 20260817"
        )

        self.assertEqual(
            self.css.count(
                marker
            ),
            1,
        )

        start = self.css.index(
            marker
        )

        end = self.css.index(
            "@media (max-width: 1180px)",
            start,
        )

        block = self.css[
            start:end
        ]

        self.assertIn(
            (
                ".mps-resizable-grid.is-molstar-expanded\n"
                "> .mw-protein-overview-sequence,"
            ),
            block,
        )

        self.assertIn(
            (
                ".mps-resizable-grid.is-molstar-expanded\n"
                "> .mps-panel-splitter {"
            ),
            block,
        )

        self.assertIn(
            "visibility: hidden;",
            block,
        )

        self.assertIn(
            "pointer-events: none;",
            block,
        )

    def test_obsolete_separator_only_comment_is_removed(
        self,
    ):
        self.assertNotIn(
            (
                "MOLSTAR EXPANDED/FULLSCREEN "
                "GUARD V2 20260817"
            ),
            self.css,
        )

        self.assertNotIn(
            (
                "Only the separator itself "
                "is suppressed."
            ),
            self.css,
        )

    def test_normal_sequence_panel_is_not_globally_hidden(
        self,
    ):
        self.assertNotIn(
            (
                ".mw-protein-overview-sequence {\n"
                "    visibility: hidden;"
            ),
            self.css,
        )

    def test_splitter_javascript_cache_remains_unchanged(
        self,
    ):
        self.assertIn(
            (
                "molecular_protein_splitter.js' %}"
                "?v=20260817-protein-splitter-v2-fullscreen"
            ),
            self.detail,
        )

    def test_splitter_css_cache_is_bumped(
        self,
    ):
        self.assertIn(
            (
                "molecular_protein_splitter.css' %}"
                "?v=20260817-protein-splitter-"
                "v3-expanded-sequence"
            ),
            self.detail,
        )

        self.assertNotIn(
            (
                "molecular_protein_splitter.css' %}"
                "?v=20260817-protein-splitter-v2-fullscreen"
            ),
            self.detail,
        )
