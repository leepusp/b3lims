from pathlib import Path

from django.test import SimpleTestCase


BASE = (
    Path(__file__).resolve().parents[1]
    / "interfaces"
    / "internal"
    / "lab_tools"
)

TEMPLATE = (
    BASE
    / "molecular_sequence_detail.html"
)

SCRIPT = (
    BASE
    / "molecular_protein_splitter.js"
)

STYLE = (
    BASE
    / "molecular_protein_splitter.css"
)


class MolecularProteinSplitterFrontendTests(
    SimpleTestCase
):
    def test_template_loads_splitter_assets(self):
        text = TEMPLATE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "molecular_protein_splitter.css",
            text,
        )

        self.assertIn(
            "molecular_protein_splitter.js",
            text,
        )

    def test_pointer_drag_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "mps-panel-splitter",
            "pointerdown",
            "pointermove",
            "pointerup",
            "pointercancel",
            "setPointerCapture",
            "releasePointerCapture",
            "pointerPercent",
            "setSplit",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_persisted_width_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "localStorage.setItem",
            "localStorage.getItem",
            "mw-protein-overview-split:",
            "DEFAULT_PERCENT",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_keyboard_and_reset_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "ArrowLeft",
            "ArrowRight",
            '"Home"',
            '"dblclick"',
            "reset:",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_molstar_resize_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'new Event(',
            text,
        )

        self.assertIn(
            '"resize"',
            text,
        )

    def test_css_uses_horizontal_resize_cursor(self):
        text = STYLE.read_text(
            encoding="utf-8"
        )

        for marker in (
            ".mps-panel-splitter",
            "cursor: col-resize",
            "--mps-sequence-panel-width",
            "grid-template-columns",
            "html.mps-resizing",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_responsive_layout_hides_splitter(self):
        text = STYLE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "@media (max-width: 1180px)",
            text,
        )

        self.assertIn(
            "display: none",
            text,
        )
