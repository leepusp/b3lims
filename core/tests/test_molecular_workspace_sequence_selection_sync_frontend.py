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

WORKSPACE = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js'
)

DETAIL = (
    BASE
    / "molecular_sequence_detail.html"
)

SYNC = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_sync.js'
)


class MolecularWorkspaceSequenceSelectionSyncTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(
        cls,
    ):
        super().setUpClass()

        cls.workspace = WORKSPACE.read_text(
            encoding="utf-8"
        )

        cls.detail = DETAIL.read_text(
            encoding="utf-8"
        )

        cls.sync = SYNC.read_text(
            encoding="utf-8"
        )

    def finish_block(
        self,
    ):
        start = self.workspace.index(
            (
                "        function "
                "finishSequenceSelection(event) {"
            )
        )

        end = self.workspace.index(
            (
                "\n        elements.preview"
                ".addEventListener("
            ),
            start,
        )

        return self.workspace[
            start:end
        ]

    def test_pointer_finish_emits_canonical_workspace_event(
        self,
    ):
        block = self.finish_block()

        self.assertIn(
            (
                "PROTEIN_WORKSPACE_SEQUENCE_"
                "SELECTION_NOTIFY_V1_20260817"
            ),
            block,
        )

        self.assertEqual(
            block.count(
                "notifyWorkspaceChange("
            ),
            1,
        )

        self.assertIn(
            '"selection"',
            block,
        )

        self.assertIn(
            '"sequence-track"',
            block,
        )

    def test_event_is_emitted_after_pointer_selection_finishes(
        self,
    ):
        block = self.finish_block()

        notify = block.index(
            "notifyWorkspaceChange("
        )

        self.assertIn(
            "state.sequenceDrag = null;",
            block,
        )

        self.assertLess(
            block.index(
                "state.sequenceDrag = null;"
            ),
            notify,
        )

    def test_direct_pointer_selection_is_still_local_during_drag(
        self,
    ):
        pointer_start = self.workspace.index(
            (
                'elements.preview.addEventListener('
                '"pointerdown"'
            )
            if (
                'elements.preview.addEventListener('
                '"pointerdown"'
            ) in self.workspace
            else (
                "elements.preview.addEventListener(\n"
                '            "pointerdown"'
            )
        )

        finish_start = self.workspace.index(
            (
                "function "
                "finishSequenceSelection(event)"
            ),
            pointer_start,
        )

        segment = self.workspace[
            pointer_start:
            finish_start
        ]

        self.assertGreaterEqual(
            segment.count(
                "state.sequenceSelection = {"
            ),
            1,
        )

        self.assertNotIn(
            "notifyWorkspaceChange(",
            segment,
        )

    def test_public_selection_api_remains_canonical(
        self,
    ):
        start = self.workspace.index(
            "function selectSequenceRange("
        )

        end = self.workspace.index(
            (
                "window.BiobankMolecularWorkspace"
                " = {"
            ),
            start,
        )

        block = self.workspace[
            start:end
        ]

        self.assertIn(
            "state.sequenceSelection = {",
            block,
        )

        self.assertIn(
            "notifyWorkspaceChange(",
            block,
        )

    def test_sync_consumes_workspace_change_event(
        self,
    ):
        self.assertIn(
            (
                '"biobank:molecular-'
                'workspace-change"'
            ),
            self.sync,
        )

        self.assertIn(
            "handleWorkspaceChange",
            self.sync,
        )

        self.assertIn(
            "snapshot.sequenceSelection",
            self.sync,
        )

    def test_focus_button_uses_synchronized_selection(
        self,
    ):
        self.assertIn(
            "function focusCurrentSelection()",
            self.sync,
        )

        self.assertIn(
            "normalizedSelection(",
            self.sync,
        )

        self.assertIn(
            "latestSelection",
            self.sync,
        )

        self.assertIn(
            "focus: true",
            self.sync,
        )

    def test_workspace_asset_is_cache_busted(
        self,
    ):
        self.assertIn(
            (
                "molecular_workspace.js' %}"
                "?v=20260817-"
                "sequence-selection-sync-v2"
            ),
            self.detail,
        )

        self.assertNotIn(
            (
                "molecular_workspace.js' %}"
                "?v=20260817-"
                "structure-coverage-v1"
            ),
            self.detail,
        )
