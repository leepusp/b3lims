from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


ROOT = Path(
    settings.BASE_DIR
)

LAB_TOOLS = (
    ROOT
    / "core"
    / "interfaces"
    / "internal"
    / "lab_tools"
)

DETAIL = (
    LAB_TOOLS
    / "molecular_sequence_detail.html"
)

PREDICTED = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_predicted_preview.js'
)

STRUCTURE = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure.js'
)

MAPPING = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_mapping.js'
)

SYNC = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_sync.js'
)


COMPUTATIONAL_EVENT = (
    "biobank:protein-computational-"
    "structure-preview-loaded"
)

PDB_EVENT = (
    "biobank:"
    "protein-structure-preview-loaded"
)


class PredictedStructurePreviewFrontendTests(
    SimpleTestCase
):
    def test_template_exposes_preview_endpoint(
        self,
    ):
        text = DETAIL.read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            text.count(
                "data-protein-structure-preview-url"
            ),
            1,
        )

        self.assertIn(
            "molecular_sequence_structure_preview_api",
            text,
        )

    def test_predicted_asset_order(
        self,
    ):
        text = DETAIL.read_text(
            encoding="utf-8"
        )

        pdb_preview = text.index(
            "molecular_protein_pdb_preview.js"
        )

        predicted = text.index(
            "molecular_protein_predicted_preview.js"
        )

        mapping = text.index(
            "molecular_protein_structure_mapping.js"
        )

        sync = text.index(
            "molecular_protein_structure_sync.js"
        )

        self.assertLess(
            pdb_preview,
            predicted,
        )

        self.assertLess(
            predicted,
            mapping,
        )

        self.assertLess(
            mapping,
            sync,
        )

    def test_browser_sends_only_canonical_key(
        self,
    ):
        text = PREDICTED.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "canonical_key:",
            text,
        )

        self.assertIn(
            "card.dataset.canonicalKey",
            text,
        )

        self.assertNotIn(
            "coordinate_url",
            text,
        )

        self.assertNotIn(
            "coordinateUrl",
            text,
        )

    def test_predicted_preview_is_same_origin(
        self,
    ):
        text = PREDICTED.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "proteinStructurePreviewUrl",
            text,
        )

        self.assertIn(
            '"same-origin"',
            text,
        )

        self.assertIn(
            '"chemical/x-cif"',
            text,
        )

    def test_predicted_cards_get_preview_action(
        self,
    ):
        text = PREDICTED.read_text(
            encoding="utf-8"
        )

        for expected in (
            ".mps-predicted-hit",
            "mps-computational-preview",
            '"Preview"',
            '"Previewing"',
            "MutationObserver",
        ):
            self.assertIn(
                expected,
                text,
            )

    def test_predicted_preview_action_is_right_aligned(
        self,
    ):
        text = PREDICTED.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "d-flex align-items-center gap-2",
            text,
        )

        self.assertIn(
            '+ "ms-auto"',
            text,
        )

        self.assertIn(
            "actions.insertBefore(",
            text,
        )

    def test_predicted_uses_separate_molstar_adapter(
        self,
    ):
        predicted = PREDICTED.read_text(
            encoding="utf-8"
        )

        structure = STRUCTURE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "loadComputationalPreviewData",
            predicted,
        )

        self.assertIn(
            "loadComputationalPreviewData",
            structure,
        )

        self.assertIn(
            COMPUTATIONAL_EVENT,
            structure,
        )

        self.assertIn(
            PDB_EVENT,
            structure,
        )

    def test_predicted_does_not_populate_pdb_identifiers(
        self,
    ):
        text = PREDICTED.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "dataset.pdbId",
            text,
        )

        self.assertNotIn(
            "dataset.entityId",
            text,
        )

        self.assertNotIn(
            "pdb_id:",
            text,
        )

    def test_mapping_builds_on_computational_preview(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            COMPUTATIONAL_EVENT,
            text,
        )

        self.assertIn(
            '"computational:"',
            text,
        )

        self.assertIn(
            "canonicalKey",
            text,
        )

        self.assertIn(
            "loadPreviewMapping({",
            text,
        )

        self.assertIn(
            "UNIVERSAL STRUCTURE MAPPING V1 20260817",
            text,
        )

    def test_sync_protects_computational_preview(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            COMPUTATIONAL_EVENT,
            text,
        )

        self.assertIn(
            "previewMode = true;",
            text,
        )

        self.assertIn(
            "activeStructure = null;",
            text,
        )

        self.assertIn(
            "bindViewerInteractions",
            text,
        )

    def test_existing_pdb_preview_event_survives(
        self,
    ):
        mapping = MAPPING.read_text(
            encoding="utf-8"
        )

        sync = SYNC.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            PDB_EVENT,
            mapping,
        )

        self.assertIn(
            PDB_EVENT,
            sync,
        )
