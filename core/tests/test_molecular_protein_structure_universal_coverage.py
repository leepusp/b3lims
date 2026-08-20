from pathlib import Path
import ast

from django.test import SimpleTestCase
from django.urls import reverse


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DETAIL = (
    ROOT
    / "core/interfaces/internal/lab_tools/"
    "molecular_sequence_detail.html"
)

TRACK = (
    ROOT
    / "core/interfaces/internal/lab_tools/"
    "molecular_sequence_track.js"
)

WORKSPACE = (
    ROOT
    / "core/interfaces/internal/lab_tools/"
    "molecular_workspace.js"
)

MAPPING = (
    ROOT
    / "core/interfaces/internal/lab_tools/"
    "molecular_protein_structure_mapping.js"
)

MAPPING_CSS = (
    ROOT
    / "core/interfaces/internal/lab_tools/"
    "molecular_protein_structure_mapping.css"
)

SYNC = (
    ROOT
    / "core/interfaces/internal/lab_tools/"
    "molecular_protein_structure_sync.js"
)

VIEW = (
    ROOT
    / "core/views/internal/lab_tools/"
    "notebook.py"
)

URLS = (
    ROOT
    / "biobank/urls.py"
)


def python_function_source(
    path,
    function_name,
):
    source = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == function_name
    ]

    if len(matches) != 1:
        raise AssertionError(
            (
                f"Expected exactly one "
                f"{function_name}, found "
                f"{len(matches)}."
            )
        )

    node = matches[0]

    lines = source.splitlines(
        keepends=True
    )

    return "".join(
        lines[
            node.lineno - 1:
            node.end_lineno
        ]
    )


class UniversalProteinStructureCoverageTests(
    SimpleTestCase
):
    def mapping_view_source(
        self,
    ):
        return python_function_source(
            VIEW,
            "molecular_sequence_pdb_mapping_api",
        )

    def test_existing_mapping_route_is_preserved(
        self,
    ):
        url = reverse(
            "molecular_sequence_pdb_mapping_api",
            args=[103],
        )

        self.assertIn(
            "103",
            url,
        )

        urls = URLS.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "molecular_sequence_pdb_mapping_api",
            urls,
        )

        self.assertNotIn(
            "molecular_sequence_structure_mapping_api",
            urls,
        )

    def test_existing_backend_is_now_source_agnostic(
        self,
    ):
        block = (
            self.mapping_view_source()
        )

        for marker in (
            "stored:<structure_id>",
            "computational:<canonical_key>",
            '"stored:"',
            '"computational:"',
            "fetch_pdb_mmcif",
            "fetch_computational_structure_preview",
            "build_structure_residue_mapping",
            "structure.file.read()",
            '"mapping_source_kind"',
        ):
            self.assertIn(
                marker,
                block,
            )

    def test_mapping_endpoint_itself_is_transient(
        self,
    ):
        block = (
            self.mapping_view_source()
        )

        for forbidden in (
            "MolecularStructure(",
            ".objects.create(",
            ".save(",
            ".bulk_create(",
        ):
            self.assertNotIn(
                forbidden,
                block,
            )

    def test_computational_key_preserves_original_case(
        self,
    ):
        block = (
            self.mapping_view_source()
        )

        self.assertIn(
            (
                "Split the ORIGINAL string, "
                "not lower_ref."
            ),
            block,
        )

        mapping = MAPPING.read_text(
            encoding="utf-8"
        )

        start = mapping.index(
            "function loadPreviewMapping"
        )

        end = mapping.index(
            "function clearMapping",
            start,
        )

        load_block = mapping[
            start:end
        ]

        self.assertNotIn(
            ".toUpperCase()",
            load_block,
        )

    def test_computational_preview_loads_real_mapping(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "biobank:"
                "protein-computational-structure-preview-loaded"
            ),
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

    def test_stored_structure_loads_real_mapping(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "STORED_STRUCTURE_EVENT",
            text,
        )

        self.assertIn(
            '"stored:"',
            text,
        )

        self.assertIn(
            "structureId",
            text,
        )

    def test_mapping_exposes_authoritative_resolved_coverage(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "function coveredRegistryPositions()",
            text,
        )

        self.assertIn(
            "resolved_registry_positions",
            text,
        )

        self.assertIn(
            "getCoveredRegistryPositions:",
            text,
        )

        self.assertIn(
            "getCoverage:",
            text,
        )

    def test_sequence_track_has_independent_coverage_state(
        self,
    ):
        text = TRACK.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "structureCoverage:",
            text,
        )

        self.assertIn(
            "is-structure-covered",
            text,
        )

        self.assertIn(
            "is-selected",
            text,
        )

        self.assertIn(
            "is-match",
            text,
        )

    def test_workspace_supplies_coverage_to_track(
        self,
    ):
        text = WORKSPACE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "structureCoverage: new Set(",
            text,
        )

        self.assertIn(
            "getCoveredRegistryPositions",
            text,
        )

        self.assertIn(
            "biobank:protein-structure-mapping-change",
            text,
        )

    def test_coverage_summary_is_rendered(
        self,
    ):
        detail = DETAIL.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "mw-structure-coverage-summary",
            detail,
        )

        mapping = MAPPING.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Resolved in active structure:",
            mapping,
        )

    def test_coverage_has_dedicated_visual_layer(
        self,
    ):
        text = MAPPING_CSS.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "PROTEIN_STRUCTURE_SEQUENCE_"
                "COVERAGE_V1_20260817"
            ),
            text,
        )

        self.assertIn(
            ".mw-base.is-structure-covered",
            text,
        )

        self.assertIn(
            "box-shadow:",
            text,
        )

    def test_stored_structure_disables_blind_number_fallback(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8"
        )

        anchor = (
            "activeStructure = (\n"
            "            event?.detail?.structure"
        )

        start = text.index(anchor)

        block = text[
            start:
            start + 900
        ]

        self.assertIn(
            "previewMode = true;",
            block,
        )

        self.assertNotIn(
            "previewMode = false;",
            block,
        )

    def test_changed_frontend_assets_are_cache_busted(
        self,
    ):
        text = DETAIL.read_text(
            encoding="utf-8"
        )

        for marker in (
            "20260817-structure-coverage-v1",
            "20260817-universal-structure-mapping-v3-chain-refocus-ui",
            "20260817-universal-structure-sync-v2-ui-copy",
        ):
            self.assertIn(
                marker,
                text,
            )
