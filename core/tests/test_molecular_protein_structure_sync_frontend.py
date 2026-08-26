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
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_sync.js'
)


class MolecularProteinStructureSyncFrontendTests(
    SimpleTestCase
):
    def test_template_loads_sync_after_structure_and_splitter(self):
        text = TEMPLATE.read_text(
            encoding="utf-8"
        )

        structure = text.index(
            "molecular_protein_structure.js"
        )

        splitter = text.index(
            "molecular_protein_splitter.js"
        )

        sync = text.index(
            "molecular_protein_structure_sync.js"
        )

        self.assertLess(
            structure,
            splitter,
        )

        self.assertLess(
            splitter,
            sync,
        )

    def test_workspace_to_molstar_selection_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "biobank:molecular-workspace-change",
            "sequenceSelection",
            "beg_auth_seq_id",
            "end_auth_seq_id",
            'action: "select"',
            "structureInteractivity",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_molstar_focus_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            'action: "focus"',
            "focusOptions",
            "extraRadius",
            "Focus selected residues",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_molstar_click_to_sequence_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "viewer.subscribe",
            "behaviors",
            "interaction",
            ".click",
            "StructureElement.Loci",
            "forEachLocation",
            "auth_seq_id",
            "label_seq_id",
            "selectSequenceRange",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_structure_reload_rebind_contract(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "biobank:protein-structure-loaded",
            "boundViewers",
            "WeakSet",
            "bindViewerInteractions",
            "getViewer",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_sync_does_not_duplicate_sequence_dom_selection(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "BiobankMolecularWorkspace",
            text,
        )

        self.assertNotIn(
            'classList.add("is-selected")',
            text,
        )

        self.assertNotIn(
            "setSelectionRange(",
            text,
        )

    def test_sync_exposes_small_public_adapter(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "BiobankProteinStructureSync",
            "selectRange:",
            "focusRange:",
            "focusSelection:",
            "getSelection:",
            "getViewer:",
        ):
            self.assertIn(
                marker,
                text,
            )
