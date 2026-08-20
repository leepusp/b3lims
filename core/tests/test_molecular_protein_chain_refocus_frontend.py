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

MAPPING = (
    BASE
    / "molecular_protein_structure_mapping.js"
)

SYNC = (
    BASE
    / "molecular_protein_structure_sync.js"
)


class ProteinMappedChainRefocusFrontendTests(
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

        cls.mapping = MAPPING.read_text(
            encoding="utf-8"
        )

        cls.sync = SYNC.read_text(
            encoding="utf-8"
        )

    def mapping_function_block(
        self,
        anchor,
    ):
        start = self.mapping.index(
            anchor
        )

        candidates = []

        for marker in (
            "\n    function ",
            "\n    async function ",
        ):
            position = self.mapping.find(
                marker,
                start + len(
                    anchor
                ),
            )

            if position > start:
                candidates.append(
                    position
                )

        end = (
            min(
                candidates
            )
            if candidates
            else len(
                self.mapping
            )
        )

        return self.mapping[
            start:end
        ]

    def test_resynchronize_has_optional_focus_policy(
        self,
    ):
        block = self.mapping_function_block(
            "function resynchronize("
        )

        self.assertIn(
            (
                "MAPPED_CHAIN_EXPLICIT_REFOCUS_"
                "V2_20260817"
            ),
            self.mapping,
        )

        self.assertIn(
            "focus = false",
            block,
        )

        self.assertIn(
            "sync?.getSelection?.()",
            block,
        )

        self.assertIn(
            "sync?.focusRange",
            block,
        )

        self.assertIn(
            "sync.focusRange(",
            block,
        )

        self.assertIn(
            "sync?.selectRange",
            block,
        )

        self.assertIn(
            "sync.selectRange(",
            block,
        )

    def test_chain_selector_requests_refocus(
        self,
    ):
        start = self.mapping.index(
            "selector.addEventListener("
        )

        end = self.mapping.index(
            "\n\n    function render()",
            start,
        )

        block = self.mapping[
            start:end
        ]

        self.assertIn(
            '"change"',
            block,
        )

        self.assertIn(
            "state.activeCandidateId",
            block,
        )

        self.assertIn(
            "resynchronize({",
            block,
        )

        self.assertIn(
            "focus: true",
            block,
        )

    def test_public_set_candidate_requests_refocus(
        self,
    ):
        start = self.mapping.index(
            "setCandidate:"
        )

        end = self.mapping.index(
            "\n            clear:",
            start,
        )

        block = self.mapping[
            start:end
        ]

        self.assertIn(
            "state.activeCandidateId",
            block,
        )

        self.assertIn(
            "resynchronize({",
            block,
        )

        self.assertIn(
            "focus: true",
            block,
        )

        self.assertIn(
            "return true",
            block,
        )

    def test_automatic_mapping_resynchronization_remains_non_focus(
        self,
    ):
        self.assertEqual(
            self.mapping.count(
                "resynchronize();"
            ),
            3,
        )

        self.assertEqual(
            self.mapping.count(
                "resynchronize({"
            ),
            2,
        )

    def test_sync_focus_primitive_is_reused_not_reimplemented(
        self,
    ):
        self.assertIn(
            "focusRange:",
            self.sync,
        )

        self.assertIn(
            "focusSelection:",
            self.sync,
        )

        self.assertIn(
            "function focusCurrentSelection()",
            self.sync,
        )

        self.assertIn(
            "focus: true",
            self.sync,
        )

    def test_registry_selection_is_reused_for_new_candidate(
        self,
    ):
        block = self.mapping_function_block(
            "function resynchronize("
        )

        self.assertIn(
            "sync?.getSelection?.()",
            block,
        )

        self.assertIn(
            "selection.start",
            block,
        )

        self.assertIn(
            "selection.end",
            block,
        )

        self.assertNotIn(
            "selectSequenceRange",
            block,
        )

    def test_mapping_asset_cache_is_bumped(
        self,
    ):
        self.assertIn(
            (
                "molecular_protein_structure_mapping.js' %}"
                "?v=20260817-"
                "universal-structure-mapping-v3-chain-refocus-ui"
            ),
            self.detail,
        )

        self.assertNotIn(
            "universal-structure-mapping-v1",
            self.detail,
        )
