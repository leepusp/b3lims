from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MolecularPlasmidMapDensityTests(
    SimpleTestCase
):
    def setUp(self):
        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        self.js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_plasmid_map.js'
        ).read_text(
            encoding="utf-8"
        )

        self.css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_plasmid_map.css'
        ).read_text(
            encoding="utf-8"
        )

        self.workspace = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js'
        ).read_text(
            encoding="utf-8"
        )

        self.template = (
            base
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

    def test_restriction_labels_have_smart_and_all_modes(
        self,
    ):
        for marker in (
            'id="mpm-restriction-label-mode"',
            'value="smart" selected>Smart',
            'value="all">All labels',
            "function restrictionLabelSites(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.js,
                )

        self.assertRegex(
            self.js,
            re.compile(
                r'''
                elements
                \s*\.\s*
                restrictionLabelMode
                \s*\.\s*
                value
                ''',
                re.VERBOSE,
            ),
        )

    def test_feature_labels_have_smart_and_all_modes(
        self,
    ):
        for marker in (
            'id="mpm-feature-label-mode"',
            "function shouldShowFeatureLabel(",
            "function smartFeatureMinimumFraction(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.js,
                )

        self.assertRegex(
            self.js,
            re.compile(
                r'''
                elements
                \s*\.\s*
                featureLabelMode
                \s*\.\s*
                value
                ''',
                re.VERBOSE,
            ),
        )

    def test_circular_smart_mode_keeps_every_cut_tick(
        self,
    ):
        self.assertIn(
            "const allSites =",
            self.js,
        )

        self.assertIn(
            "allSites.forEach",
            self.js,
        )

        self.assertIn(
            "restrictionLabelSites(",
            self.js,
        )

    def test_linear_smart_mode_keeps_every_cut_tick(
        self,
    ):
        self.assertIn(
            "const allLinearSites =",
            self.js,
        )

        self.assertIn(
            "allLinearSites.forEach",
            self.js,
        )

        self.assertIn(
            "const linearLabelSites =",
            self.js,
        )

        self.assertIn(
            "linearLabelSites.forEach",
            self.js,
        )

    def test_complete_site_list_remains_available(
        self,
    ):
        for marker in (
            'id="mpm-toggle-site-list"',
            'id="mpm-site-list-panel"',
            "function renderSiteList(",
            "filteredRestrictionSites()",
            "siteListItems",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_smart_density_is_zoom_aware(
        self,
    ):
        for marker in (
            "function currentZoomFactor()",
            "DEFAULT_VIEW_BOX.width",
            "state.viewBox.width",
            "Math.ceil(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_status_reports_that_ticks_are_preserved(
        self,
    ):
        self.assertIn(
            "matching cut ticks retained",
            self.js,
        )

        self.assertIn(
            (
                "Zoom in for more labels, "
                "open Sites list, or choose All labels."
            ),
            self.js,
        )

    def test_sequence_selection_contract_is_available(
        self,
    ):
        self.assertIn(
            "function selectSequenceRange(",
            self.workspace,
        )

        self.assertRegex(
            self.workspace,
            re.compile(
                r'''
                selectSequenceRange
                \s*,
                ''',
                re.VERBOSE,
            ),
        )

    def test_density_styles_exist(
        self,
    ):
        for marker in (
            ".mpm-density-note",
            ".mpm-site-list-panel",
            ".mpm-site-list-items",
            ".mpm-site-list-item",
            ".mpm-site-list-item.is-selected",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.css,
                )

    def test_template_uses_density_asset_version(
        self,
    ):
        expected_assets = (
            (
                "molecular_plasmid_map.css"
                "' %}?v=20260810-final-ux-v2"
            ),
            (
                "molecular_plasmid_map.js"
                "' %}?v=20260810-final-ux-v2"
            ),
        )

        for marker in expected_assets:
            with self.subTest(
                marker=marker,
            ):
                self.assertIn(
                    marker,
                    self.template,
                )

        self.assertNotIn(
            (
                "20260807-"
                "detailed-plasmid-map-"
                "v3-density"
            ),
            self.template,
        )
