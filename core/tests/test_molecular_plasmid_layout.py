from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MolecularPlasmidLayoutTests(
    SimpleTestCase
):
    def setUp(self):
        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        self.js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_plasmid_layout.js'
        ).read_text(
            encoding="utf-8"
        )

        self.css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_plasmid_layout.css'
        ).read_text(
            encoding="utf-8"
        )

        self.template = (
            base
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

    def test_map_size_modes_exist(
        self,
    ):
        for marker in (
            'id="mpl-map-size"',
            'value="auto"',
            'value="large"',
            'value="xl"',
            'value="fit"',
            "function mapHeight()",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_internal_feature_spacing_is_additive(
        self,
    ):
        for marker in (
            'id="mpl-smart-feature-spacing"',
            "function reflowFeatureLabels()",
            "mplOriginalX",
            "mplOriginalY",
            "mpl-feature-label-leader",
            "restoreLabels",
            "boxesOverlap",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_layout_does_not_replace_molecular_data(
        self,
    ):
        self.assertIn(
            (
                "biobank:"
                "molecular-workspace-change"
            ),
            self.js,
        )

        self.assertNotIn(
            "fetch(",
            self.js,
        )

        self.assertNotIn(
            "save",
            self.js.lower(),
        )

    def test_layout_styles_exist(
        self,
    ):
        for marker in (
            "--mpl-map-height",
            ".mpl-layout-controls",
            ".mpl-feature-label-spaced",
            ".mpl-feature-label-leader",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.css,
                )

    def test_template_loads_layout_assets(
        self,
    ):
        self.assertIn(
            "molecular_plasmid_layout.css",
            self.template,
        )

        self.assertIn(
            "molecular_plasmid_layout.js",
            self.template,
        )

        token = (
            "20260807-"
            "molecular-layout-browser-v1"
        )

        self.assertEqual(
            self.template.count(token),
            2,
        )

        self.assertIn(
            (
                "molecular_plasmid_layout.css"
                "' %}?v="
                + token
            ),
            self.template,
        )

        self.assertIn(
            (
                "molecular_plasmid_layout.js"
                "' %}?v="
                + token
            ),
            self.template,
        )
