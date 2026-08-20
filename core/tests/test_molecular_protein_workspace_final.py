from pathlib import Path

from django.test import SimpleTestCase


BASE = (
    Path(__file__)
    .resolve()
    .parents[1]
    / "interfaces"
    / "internal"
    / "lab_tools"
)


class MolecularProteinFinalWorkspaceTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.template = (
            BASE
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

        cls.js = (
            BASE
            / "molecular_protein_alignment.js"
        ).read_text(
            encoding="utf-8"
        )

        cls.css = (
            BASE
            / "molecular_protein_alignment.css"
        ).read_text(
            encoding="utf-8"
        )

    def test_template_loads_only_final_protein_assets(
        self,
    ):
        expected_assets = (
            "molecular_protein_alignment.css' %}?v=20260814-protein-palette-v1",
            "molecular_workspace.js' %}?v=20260817-sequence-selection-sync-v2",
            "molecular_protein_alignment.js' %}?v=20260814-protein-palette-v1",
        )

        for asset in expected_assets:
            with self.subTest(
                asset=asset
            ):
                self.assertIn(
                    asset,
                    self.template,
                )

        for forbidden in (
            "molecular_protein_overview.css",
            "molecular_protein_overview.js",
            "nightingale-protein-5.6.0.min.js",
            "data-protein-msa-vendor-url",
        ):
            with self.subTest(
                forbidden=forbidden
            ):
                self.assertNotIn(
                    forbidden,
                    self.template,
                )

    def test_final_workspace_has_two_primary_views(
        self,
    ):
        for marker in (
            "PROTEIN FINAL WORKSPACE V1 20260812",
            "mw-protein-final-tabs",
            "mw-protein-final-overview",
            "mw-protein-final-alignment",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

        self.assertNotIn(
            "PROTEIN WORKSPACE P3B 20260812",
            self.js,
        )

    def test_existing_sequence_card_becomes_overview(
        self,
    ):
        for marker in (
            '".mw-sequence-card"',
            '"mw-protein-overview-sequence"',
            "overviewPane.appendChild(",
            (
                '"Complete amino-acid sequence with synchronized "'
            ),
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_annotations_are_integrated_not_primary_view(
        self,
    ):
        for marker in (
            '"mw-unified-feature-editor"',
            '"mw-protein-annotation-details"',
            '"Edit annotations"',
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_alignment_renders_actual_amino_acids(
        self,
    ):
        for marker in (
            "PROTEIN TEXT MSA V1 20260812",
            "payload.rows",
            "MSA_BLOCK_SIZE = 80",
            "makeResidueCell(",
            "mpa-residue",
            "mpa-alignment-block",
            '"Consensus"',
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_nightingale_alignment_runtime_is_removed(
        self,
    ):
        for forbidden in (
            "nightingale-msa",
            "proteinMsaVendorUrl",
            "vendorPromise",
            "loadVendor(",
            "viewerResizeObserver",
            "disconnectViewerResizeObserver(",
            "viewerViewportWidth(",
            "setViewerWidth(",
            "observeViewerWidth(",
        ):
            with self.subTest(
                forbidden=forbidden
            ):
                self.assertNotIn(
                    forbidden,
                    self.js,
                )

    def test_msa_css_keeps_characters_visible(
        self,
    ):
        for marker in (
            ".mpa-residue",
            "font-weight: 700;",
            "user-select: text;",
            ".mpa-alignment-label",
            ".mpa-consensus-row",
            ".mpa-alignment-block-scroll",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.css,
                )

    def test_existing_outer_expand_contract_is_preserved(
        self,
    ):
        self.assertIn(
            ".is-workspace-maximized",
            self.css,
        )

        self.assertIn(
            ".mw-protein-final-stage",
            self.css,
        )


class MolecularProteinFinalCleanupTests(
    SimpleTestCase
):
    def test_retired_frontend_files_are_absent(
        self,
    ):
        retired = (
            BASE
            / "molecular_protein_overview.js",
            BASE
            / "molecular_protein_overview.css",
            BASE
            / "vendor"
            / "nightingale-protein-5.6.0.min.js",
            BASE
            / "vendor"
            / "nightingale-protein-5.6.0.LICENSES.txt",
            BASE
            / "vendor"
            / "nightingale-msa-5.6.0.min.js",
            BASE
            / "vendor"
            / "nightingale-msa-5.6.0.LICENSES.txt",
        )

        for retired_path in retired:
            with self.subTest(
                path=retired_path.name
            ):
                self.assertFalse(
                    retired_path.exists()
                )

    def test_phase_specific_test_files_are_absent(
        self,
    ):
        test_dir = (
            Path(__file__)
            .resolve()
            .parent
        )

        retired = (
            "test_molecular_protein_overview.py",
            "test_molecular_protein_refinement.py",
            "test_molecular_protein_runtime_fixes.py",
            "test_molecular_protein_workspace_p3.py",
            "test_molecular_protein_workspace_p3b.py",
        )

        for name in retired:
            with self.subTest(name=name):
                self.assertFalse(
                    (
                        test_dir
                        / name
                    ).exists()
                )

    def test_final_runtime_reuses_shared_dom(
        self,
    ):
        js = (
            BASE
            / "molecular_protein_alignment.js"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '".mw-sequence-card"',
            js,
        )

        self.assertIn(
            '"mw-unified-feature-editor"',
            js,
        )

        self.assertNotIn(
            "cloneNode(",
            js,
        )


class MolecularProteinResiduePaletteTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.js = (
            BASE
            / "molecular_protein_alignment.js"
        ).read_text(
            encoding="utf-8"
        )

        cls.css = (
            BASE
            / "molecular_protein_alignment.css"
        ).read_text(
            encoding="utf-8"
        )

    def test_residue_palette_runtime_is_present(
        self,
    ):
        for marker in (
            "PROTEIN RESIDUE PALETTE V1 20260814",
            "mw-protein-residue-palette",
            "Residue colors",
            "High contrast",
            "Monochrome",
            "mw-protein-palette-control",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_residue_palette_styles_are_present(
        self,
    ):
        for marker in (
            'data-residue-palette="soft"',
            'data-residue-palette="contrast"',
            'data-residue-palette="mono"',
            ".mw-protein-palette-select",
            "#mw-sequence-preview .mw-base",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.css,
                )
