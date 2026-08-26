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

SYNC = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_sync.js'
)

PREVIEW = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_pdb_preview.js'
)

MAPPING = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_mapping.js'
)

MAPPING_CSS = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure_mapping.css'
)


class MolecularProteinStructureMappingFrontendTests(
    SimpleTestCase
):
    def test_template_exposes_mapping_api(
        self,
    ):
        text = TEMPLATE.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "data-protein-pdb-mapping-url",
            text,
        )

        self.assertIn(
            "molecular_sequence_pdb_mapping_api",
            text,
        )

    def test_template_loads_mapping_before_sync(
        self,
    ):
        text = TEMPLATE.read_text(
            encoding="utf-8",
        )

        mapping = text.index(
            "molecular_protein_structure_mapping.js"
        )

        sync = text.index(
            "molecular_protein_structure_sync.js"
        )

        self.assertLess(
            mapping,
            sync,
        )

    def test_cache_versions_changed_for_modified_assets(
        self,
    ):
        text = TEMPLATE.read_text(
            encoding="utf-8",
        )

        expected_versions = (
            "protein-pdb-preview-v2",
            "protein-structure-v4-ui-copy",
            "predicted-preview-v3-ui-copy",
            "universal-structure-mapping-v3-chain-refocus-ui",
            "universal-structure-sync-v2-ui-copy",
        )

        for marker in expected_versions:
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    text,
                )

        stale_versions = (
            "protein-structure-v2",
            "protein-structure-mapping-v2",
            "protein-structure-sync-v4",
        )

        for marker in stale_versions:
            with self.subTest(
                stale_marker=marker,
            ):
                self.assertNotIn(
                    marker,
                    text,
                )

    def test_preview_extracts_polymer_entity(
        self,
    ):
        text = PREVIEW.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "entityIdFromCard",
            text,
        )

        self.assertIn(
            r"\bentity\s+",
            text,
        )

        self.assertIn(
            "entityId,",
            text,
        )

        self.assertIn(
            "getActiveEntityId",
            text,
        )

    def test_preview_removed_old_mapping_pending_override(
        self,
    ):
        text = PREVIEW.read_text(
            encoding="utf-8",
        )

        self.assertNotIn(
            (
                "PDB Preview mode · residue mapping "
                "+ \"is required before sequence ↔ 3D \""
            ),
            text,
        )

    def test_mapping_fetches_server_side_api(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "proteinPdbMappingUrl",
            text,
        )

        self.assertIn(
            "credentials:",
            text,
        )

        self.assertIn(
            '"same-origin"',
            text,
        )

        self.assertIn(
            '"entity_id"',
            text,
        )

    def test_mapping_exposes_ranked_chain_selector(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "Mapped chain",
            text,
        )

        self.assertIn(
            "resolved",
            text,
        )

        self.assertIn(
            "identity",
            text,
        )

        self.assertIn(
            "resolved coordinates",
            text,
        )

        self.assertIn(
            "setCandidate",
            text,
        )

    def test_forward_mapping_uses_mmcif_label_ids(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        for marker in (
            "label_asym_id",
            "beg_label_seq_id",
            "end_label_seq_id",
            "groupedElements",
            "mapSelection",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_unresolved_region_has_explicit_message(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "has no resolved",
            text,
        )

        self.assertIn(
            "coordinates for this region",
            text,
        )

    def test_reverse_mapping_supports_both_id_namespaces(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        for marker in (
            "registryPositionForResidue",
            "labelAsymId",
            "labelSeqId",
            "authAsymId",
            "authSeqId",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_loci_adapter_preserves_both_chain_ids(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "authAsymId:",
            text,
        )

        self.assertIn(
            "labelAsymId:",
            text,
        )

    def test_preview_mode_cannot_fall_back_to_auth_seq_id(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "previewMode",
            text,
        )

        self.assertIn(
            "Sequence-to-structure synchronization is disabled",
            text,
        )

        self.assertIn(
            "Never use the legacy auth_seq_id fallback",
            text,
        )

    def test_reverse_mapping_translates_before_workspace(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "registryPositionForResidue",
            text,
        )

        self.assertIn(
            "registryCoordinate",
            text,
        )

        self.assertIn(
            (
                "workspace.selectSequenceRange(\n"
                "            registryCoordinate,"
            ),
            text,
        )

    def test_preview_event_is_bound_by_sync(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "PREVIEW_EVENT",
            text,
        )

        self.assertIn(
            "biobank:protein-structure-preview-loaded",
            text,
        )

    def test_stored_structure_legacy_fallback_is_retained(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "beg_auth_seq_id",
            text,
        )

        self.assertIn(
            "end_auth_seq_id",
            text,
        )

        self.assertIn(
            "Legacy direct-coordinate fallback",
            text,
        )

    def test_mapping_builds_exact_molstar_schema(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "PROTEIN_STRUCTURE_MAPPING_EXACT_SCHEMA_V2_20260815",
            text,
        )

        self.assertIn(
            "function exactSelectionSchema(",
            text,
        )

        self.assertIn(
            "label_asym_id:",
            text,
        )

        self.assertIn(
            "label_seq_id:",
            text,
        )

        self.assertIn(
            "schema:",
            text,
        )

    def test_sync_uses_one_atomic_mapped_schema_operation(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "PROTEIN_STRUCTURE_SYNC_ATOMIC_SCHEMA_V3_20260815",
            text,
        )

        self.assertIn(
            "mapped.schema?.items",
            text,
        )

        self.assertIn(
            "mapped.schema",
            text,
        )

        self.assertNotIn(
            "of mapped.elements",
            text,
        )

    def test_chain_selector_remains_available(
        self,
    ):
        text = MAPPING.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "Mapped chain",
            text,
        )

        self.assertIn(
            "setCandidate",
            text,
        )

        self.assertIn(
            "activeCandidateId",
            text,
        )

    def test_sync_hydrates_preexisting_workspace_selection(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "PROTEIN_STRUCTURE_SYNC_WORKSPACE_HYDRATION_V4_20260815",
            text,
        )

        self.assertIn(
            "function applyWorkspaceSnapshot(",
            text,
        )

        self.assertIn(
            "function hydrateWorkspaceSnapshot()",
            text,
        )

        self.assertIn(
            "workspace.getSnapshot()",
            text,
        )

        self.assertIn(
            "applyWorkspaceSnapshot(",
            text,
        )

    def test_preview_refreshes_workspace_snapshot_before_sync(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        start = text.index(
            "root.addEventListener(\n"
            "            PREVIEW_EVENT,"
        )

        end = text.index(
            "const existingMappingAdapter",
            start,
        )

        preview_segment = text[
            start:end
        ]

        self.assertIn(
            "hydrateWorkspaceSnapshot();",
            preview_segment,
        )

        self.assertIn(
            "selectMolstarRange(",
            preview_segment,
        )

        self.assertLess(
            preview_segment.index(
                "hydrateWorkspaceSnapshot();"
            ),
            preview_segment.index(
                "selectMolstarRange("
            ),
        )

    def test_initialization_recovers_active_preview_mapping(
        self,
    ):
        text = SYNC.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "existingMappingAdapter.isActive()",
            text,
        )

        self.assertIn(
            "previewMode = true;",
            text,
        )

        self.assertIn(
            "hydrateWorkspaceSnapshot();",
            text,
        )

    def test_hydration_preserves_mapped_chain_selector(
        self,
    ):
        mapping = MAPPING.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "Mapped chain",
            mapping,
        )

        self.assertIn(
            "setCandidate",
            mapping,
        )

        self.assertIn(
            "activeCandidateId",
            mapping,
        )

    def test_mapping_css_is_responsive(
        self,
    ):
        text = MAPPING_CSS.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            ".mps-structure-mapping-controls",
            text,
        )

        self.assertIn(
            "flex-wrap: wrap",
            text,
        )
