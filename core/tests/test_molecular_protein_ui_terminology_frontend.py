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
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_mapping.js'
)

SYNC = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_sync.js'
)

PREDICTED = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_predicted_preview.js'
)

FINDER = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_pdb_search.js'
)

STRUCTURE = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure.js'
)


class ProteinUiTerminologyFrontendTests(
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

        cls.predicted = PREDICTED.read_text(
            encoding="utf-8"
        )

        cls.finder = FINDER.read_text(
            encoding="utf-8"
        )

        cls.structure = STRUCTURE.read_text(
            encoding="utf-8"
        )

    def test_active_structure_summary_is_explicit(
        self,
    ):
        self.assertIn(
            "Resolved in active structure:",
            self.mapping,
        )

        self.assertNotIn(
            "Structure coverage:",
            self.mapping,
        )

    def test_candidate_metrics_use_clear_terms(
        self,
    ):
        self.assertIn(
            " identity",
            self.mapping,
        )

        self.assertIn(
            "alignment coverage",
            self.mapping,
        )

        self.assertIn(
            "resolved coordinates",
            self.mapping,
        )

        self.assertNotIn(
            "sequence coverage",
            self.mapping,
        )

        self.assertNotIn(
            "coordinate coverage",
            self.mapping,
        )

    def test_sync_warning_is_structure_source_neutral(
        self,
    ):
        self.assertEqual(
            self.sync.count(
                (
                    "Structure residue mapping "
                    "is not available."
                )
            ),
            2,
        )

        self.assertNotIn(
            (
                "PDB Preview residue mapping "
                "is not available."
            ),
            self.sync,
        )

        self.assertIn(
            (
                "Sequence-to-structure "
                "synchronization is disabled "
            ),
            self.sync,
        )

    def test_predicted_preview_no_longer_claims_mapping_unavailable(
        self,
    ):
        self.assertNotIn(
            "residue mapping unavailable",
            self.predicted,
        )

        self.assertIn(
            " · temporary · not saved",
            self.predicted,
        )

    def test_computational_preview_no_longer_claims_mapping_unavailable(
        self,
    ):
        self.assertNotIn(
            "residue mapping unavailable",
            self.structure,
        )

        self.assertIn(
            '"not saved"',
            self.structure,
        )

    def test_structure_finder_describes_unified_search(
        self,
    ):
        self.assertIn(
            (
                "Search available experimental "
                "and predicted structures "
            ),
            self.finder,
        )

        self.assertIn(
            (
                "across supported structure "
                "databases and model providers."
            ),
            self.finder,
        )

    def test_structure_finder_predicted_preview_note_is_current(
        self,
    ):
        self.assertIn(
            (
                "Predicted structures can be "
                "previewed temporarily in Mol* "
            ),
            self.finder,
        )

        self.assertIn(
            "and are not saved.",
            self.finder,
        )

        self.assertNotIn(
            "enabled in the next integration phase.",
            self.finder,
        )

    def test_changed_javascript_assets_have_exact_new_cache_markers(
        self,
    ):
        markers = (
            (
                "molecular_protein_structure.js' %}"
                "?v=20260816-protein-structure-v4-ui-copy"
            ),
            (
                "molecular_protein_pdb_search.js' %}"
                "?v=20260816-find-structure-v2-ui-copy"
            ),
            (
                "molecular_protein_predicted_preview.js' %}"
                "?v=20260816-predicted-preview-v3-ui-copy"
            ),
            (
                "molecular_protein_structure_mapping.js' %}"
                "?v=20260817-universal-structure-mapping-"
                "v3-chain-refocus-ui"
            ),
            (
                "molecular_protein_structure_sync.js' %}"
                "?v=20260817-universal-structure-sync-v2-ui-copy"
            ),
        )

        for marker in markers:
            with self.subTest(
                marker=marker,
            ):
                self.assertEqual(
                    self.detail.count(
                        marker
                    ),
                    1,
                )

    def test_finder_css_cache_is_intentionally_unchanged(
        self,
    ):
        self.assertEqual(
            self.detail.count(
                (
                    "molecular_protein_pdb_search.css' %}"
                    "?v=20260816-find-structure-v1"
                )
            ),
            1,
        )

        self.assertEqual(
            self.detail.count(
                "find-structure-v1"
            ),
            1,
        )

        self.assertEqual(
            self.detail.count(
                "find-structure-v2-ui-copy"
            ),
            1,
        )

    def test_chain_refocus_policy_is_preserved(
        self,
    ):
        self.assertIn(
            "MAPPED_CHAIN_EXPLICIT_REFOCUS_V2_20260817",
            self.mapping,
        )

        self.assertEqual(
            self.mapping.count(
                "resynchronize({"
            ),
            2,
        )

        self.assertEqual(
            self.mapping.count(
                "resynchronize();"
            ),
            3,
        )

    def test_atomic_mapped_select_focus_is_preserved(
        self,
    ):
        expected = """                action: (
                    focus
                        ? [
                            "select",
                            "focus",
                        ]
                        : "select"
                ),
"""

        self.assertEqual(
            self.sync.count(
                expected
            ),
            1,
        )

        self.assertIn(
            "focusRange:",
            self.sync,
        )

        self.assertIn(
            "focusSelection:",
            self.sync,
        )
