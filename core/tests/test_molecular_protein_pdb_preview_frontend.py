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

STRUCTURE_SCRIPT = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure.js'
)

PREVIEW_SCRIPT = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_pdb_preview.js'
)

PREVIEW_STYLE = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_pdb_preview.css'
)


class MolecularProteinPdbPreviewFrontendTests(
    SimpleTestCase
):
    def test_template_exposes_preview_url(self):
        text = TEMPLATE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "data-protein-pdb-preview-url",
            text,
        )

        self.assertIn(
            "molecular_sequence_pdb_preview_api",
            text,
        )

    def test_template_loads_preview_assets(self):
        text = TEMPLATE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "molecular_protein_pdb_preview.js",
            text,
        )

        self.assertIn(
            "molecular_protein_pdb_preview.css",
            text,
        )

    def test_toolbar_uses_clear_english_actions(self):
        text = STRUCTURE_SCRIPT.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Load stored structure",
            text,
        )

        self.assertIn(
            "Upload structure",
            text,
        )

        self.assertIn(
            "uploadInput.hidden = true",
            text,
        )

        self.assertIn(
            "uploadInput.click()",
            text,
        )

    def test_preview_enhances_existing_pdb_results(self):
        text = PREVIEW_SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            ".mps-pdb-hit",
            ".mps-pdb-hit-id",
            "Preview",
            "Previewing",
            "proteinPdbPreviewUrl",
            "MutationObserver",
            "loadPreviewData",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_preview_uses_authenticated_backend(self):
        text = PREVIEW_SCRIPT.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'credentials:\n                            "same-origin"',
            text,
        )

        self.assertIn(
            '"Accept":\n                                "chemical/x-cif"',
            text,
        )

    def test_preview_does_not_persist_structure(self):
        text = PREVIEW_SCRIPT.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "Add to record",
            text,
        )

        self.assertNotIn(
            "FormData",
            text,
        )

        self.assertIn(
            "temporary · not saved",
            text,
        )

    def test_structure_adapter_exposes_transient_loader(self):
        text = STRUCTURE_SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "loadPreviewData",
            "biobank:protein-structure-preview-loaded",
            "residue mapping pending",
            'loadStructureFromData(',
            '"mmcif"',
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_preview_card_state_is_styled(self):
        text = PREVIEW_STYLE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ".mps-pdb-hit.is-previewing",
            text,
        )

        self.assertIn(
            ".mps-pdb-preview-actions",
            text,
        )

    def test_application_does_not_define_portuguese_controls(
        self,
    ):
        combined = (
            STRUCTURE_SCRIPT.read_text(
                encoding="utf-8"
            )
            + PREVIEW_SCRIPT.read_text(
                encoding="utf-8"
            )
        )

        for label in (
            "Escolher arquivo",
            "Nenhum arquivo escolhido",
            "Nenhum arquivo selecionado",
            "Carregar estrutura",
            "Enviar estrutura",
        ):
            self.assertNotIn(
                label,
                combined,
            )
