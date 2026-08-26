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

SCRIPT = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_splitter.js'
)

STYLE = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_splitter.css'
)

TEMPLATE = (
    BASE
    / "molecular_sequence_detail.html"
)


class MolecularProteinSplitterFullscreenTests(
    SimpleTestCase
):
    def setUp(
        self,
    ):
        self.script = SCRIPT.read_text(
            encoding="utf-8"
        )

        self.style = STYLE.read_text(
            encoding="utf-8"
        )

        self.template = TEMPLATE.read_text(
            encoding="utf-8"
        )

    def test_splitter_tracks_molstar_layout_state(
        self,
    ):
        for marker in (
            "plugin",
            "layout",
            "events",
            "updated",
            "isExpanded",
            "expandToFullscreen",
            "msp-layout-expanded",
        ):
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    self.script,
                )

    def test_browser_fullscreen_is_also_supported(
        self,
    ):
        for marker in (
            "document.fullscreenElement",
            "fullscreenchange",
            "webkitfullscreenchange",
        ):
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    self.script,
                )

    def test_expanded_state_hides_only_separator(
        self,
    ):
        self.assertIn(
            "is-molstar-expanded",
            self.script,
        )

        self.assertIn(
            (
                ".mps-resizable-grid.is-molstar-expanded"
            ),
            self.style,
        )

        self.assertIn(
            "visibility: hidden;",
            self.style,
        )

        self.assertIn(
            "pointer-events: none;",
            self.style,
        )

        #
        # Keep the grid column intact rather than switching the
        # entire grid to another column definition.
        #
        guard_start = self.style.index(
            (
                ".mps-resizable-grid."
                "is-molstar-expanded"
            )
        )

        guard_end = self.style.index(
            "@media (max-width: 1180px)",
            guard_start,
        )

        guard = self.style[
            guard_start:
            guard_end
        ]

        self.assertNotIn(
            "display: none;",
            guard,
        )

        self.assertNotIn(
            "grid-template-columns",
            guard,
        )

    def test_expanded_state_cancels_active_drag(
        self,
    ):
        for marker in (
            "activePointerId",
            "cancelResize",
            "releasePointerCapture",
            'grid.classList.contains(',
            '"is-molstar-expanded"',
        ):
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    self.script,
                )

    def test_saved_split_preference_is_preserved(
        self,
    ):
        self.assertIn(
            "window.localStorage.setItem",
            self.script,
        )

        self.assertIn(
            "window.localStorage.getItem",
            self.script,
        )

        self.assertNotIn(
            "window.localStorage.removeItem",
            self.script,
        )

        self.assertNotIn(
            "window.localStorage.clear",
            self.script,
        )

    def test_splitter_becomes_non_focusable_when_expanded(
        self,
    ):
        self.assertIn(
            '"aria-hidden"',
            self.script,
        )

        self.assertIn(
            "splitter.tabIndex",
            self.script,
        )

        self.assertIn(
            "? -1",
            self.script,
        )

    def test_mutation_observer_is_dom_fallback(
        self,
    ):
        for marker in (
            "MutationObserver",
            "structurePanel",
            "subtree: true",
            'attributeFilter: [',
            '"class"',
        ):
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    self.script,
                )

    def test_structure_load_events_rebind_viewer(
        self,
    ):
        for marker in (
            "biobank:protein-structure-loaded",
            "biobank:protein-pdb-preview-loaded",
            (
                "protein-computational-"
                "structure-preview-loaded"
            ),
            "bindViewerLayout",
        ):
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    self.script,
                )

    def test_splitter_cache_is_bumped(
        self,
    ):
        self.assertIn(
            (
                "molecular_protein_splitter.css' %}?v=20260817-protein-splitter-v3-expanded-sequence"
            ),
            self.template,
        )

        self.assertIn(
            (
                "molecular_protein_splitter.js' %}?"
                "v=20260817-protein-splitter-v2-fullscreen"
            ),
            self.template,
        )

        self.assertNotIn(
            (
                "molecular_protein_splitter.js' %}?"
                "v=20260815-protein-splitter-v1"
            ),
            self.template,
        )
