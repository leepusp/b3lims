from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


ROOT = Path(
    settings.BASE_DIR
)

DETAIL = (
    ROOT
    / "core"
    / "interfaces"
    / "internal"
    / "lab_tools"
    / "molecular_sequence_detail.html"
)

FINDER_JS = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_pdb_search.js'
)

FINDER_CSS = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_pdb_search.css'
)


class MolecularProteinStructureFinderFrontendTests(
    SimpleTestCase
):
    def test_template_exposes_unified_structure_search_api(
        self,
    ):
        text = DETAIL.read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            text.count(
                "data-protein-structure-search-url"
            ),
            1,
        )

        self.assertIn(
            "molecular_sequence_structure_search_api",
            text,
        )

        self.assertIn(
            "data-protein-pdb-search-url",
            text,
        )

        self.assertIn(
            "data-protein-pdb-preview-url",
            text,
        )

        self.assertIn(
            "data-protein-pdb-mapping-url",
            text,
        )

    def test_template_uses_new_finder_asset_version(
        self,
    ):
        text = DETAIL.read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            text.count(
                "20260816-find-structure-v2-ui-copy"
            ),
            1,
        )

    def test_finder_uses_unified_api_and_labels(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        for expected in (
            "proteinStructureSearchUrl",
            "Find structure",
            "Structure Finder",
            "Search structures",
            '"All"',
            '"Experimental"',
            '"Predicted"',
        ):
            self.assertIn(
                expected,
                text,
            )

        self.assertNotIn(
            "Find in PDB",
            text,
        )

        self.assertNotIn(
            "Searching RCSB PDB",
            text,
        )

    def test_finder_consumes_normalized_structure_hit_fields(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        for expected in (
            "hit?.source_type",
            "hit?.provider",
            "hit?.provider_name",
            "hit?.accession",
            "hit?.canonical_key",
            "hit?.entity_id",
            "hit?.sequence_coverage",
            "hit?.model_coverage",
            "hit?.experimental_method",
            "hit?.resolution",
            "hit?.confidence_type",
            "hit?.confidence_value",
            "hit?.sequence_accession",
        ):
            self.assertIn(
                expected,
                text,
            )

        self.assertNotIn(
            "hit.query_coverage",
            text,
        )

        self.assertNotIn(
            "hit.evalue",
            text,
        )

        self.assertNotIn(
            "hit.pdb_id",
            text,
        )

    def test_unified_request_uses_rows_only(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'rows: "10"',
            text,
        )

        self.assertNotIn(
            "identity.value",
            text,
        )

        self.assertNotIn(
            "evalue.value",
            text,
        )

    def test_experimental_cards_preserve_pdb_preview_contract(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        for expected in (
            '" mps-pdb-hit"',
            '"mps-pdb-hit-id "',
            "card.dataset.pdbId",
            "card.dataset.entityId",
            "isExperimental(hit)",
        ):
            self.assertIn(
                expected,
                text,
            )

    def test_predicted_cards_are_isolated_from_pdb_preview(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '" mps-predicted-hit"',
            text,
        )

        self.assertIn(
            (
                "Predicted cards NEVER receive "
                "mps-pdb-hit"
            ),
            text,
        )

        self.assertIn(
            "Predicted structures can be previewed temporarily in Mol* ",
            text,
        )

        self.assertIn(
            "and are not saved.",
            text,
        )

    def test_no_direct_external_coordinate_fetch(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "fetch(hit.coordinate_url",
            text,
        )

        self.assertNotIn(
            "fetch(hit?.coordinate_url",
            text,
        )

    def test_filtering_is_local_after_unified_search(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        for expected in (
            "activeFilter",
            "filteredHits",
            "updateFilterButtons",
            "dataset.structureFilter",
            "state.hits.filter",
        ):
            self.assertIn(
                expected,
                text,
            )

    def test_finder_preserves_established_dom_ids(
        self,
    ):
        text = FINDER_JS.read_text(
            encoding="utf-8"
        )

        for expected in (
            '"mps-pdb-find"',
            '"mps-pdb-finder"',
            '"mps-pdb-search"',
            '"mps-pdb-summary"',
            '"mps-pdb-results"',
        ):
            self.assertIn(
                expected,
                text,
            )

    def test_css_supports_unified_and_legacy_preview_surface(
        self,
    ):
        text = FINDER_CSS.read_text(
            encoding="utf-8"
        )

        for expected in (
            ".mps-structure-finder",
            ".mps-structure-filters",
            ".mps-structure-filter",
            ".mps-structure-hit",
            ".mps-pdb-hit",
            ".mps-structure-source-badge",
            ".mps-structure-source-badge.is-predicted",
            ".mps-structure-preview-note",
            "@media",
        ):
            self.assertIn(
                expected,
                text,
            )
