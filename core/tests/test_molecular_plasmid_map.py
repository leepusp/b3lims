from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularFeature,
    MolecularSequence,
)


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    ).removeprefix(
        "/biobank"
    )


class MolecularPlasmidMapStaticTests(
    SimpleTestCase
):
    def setUp(self):
        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        self.js = (
            base
            / "molecular_plasmid_map.js"
        ).read_text(
            encoding="utf-8"
        )

        self.css = (
            base
            / "molecular_plasmid_map.css"
        ).read_text(
            encoding="utf-8"
        )

    def test_uses_shared_workspace_contract(
        self,
    ):
        markers = (
            "window.BiobankMolecularWorkspace",
            "biobank:molecular-workspace-change",
            "event.detail?.snapshot",
            "selectFeature",
            "selectSequenceRange",
            "refresh",
        )

        for marker in markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_uses_restriction_analysis_backend(
        self,
    ):
        markers = (
            "root.dataset",
            "restrictionSitesUrl",
            '"X-CSRFToken"',
            "mode:",
            "restrictionMode",
            "minimum_site_length",
            "selected_enzymes",
            'value="unique"',
            'value="selected"',
            "cutting_enzyme_count",
            "unique_cutter_count",
        )

        for marker in markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_svg_map_features_are_present(
        self,
    ):
        js_markers = (
            "assignCircularFeatureLanes",
            "distributeVerticalLabels",
            "mpm-feature-arrow",
            "mpm-restriction-leader",
            "mpm-restriction-label",
            "pointerdown",
            '"wheel"',
            "XMLSerializer",
            "SVG_EXPORT_STYLE",
            "Detailed map",
        )

        for marker in js_markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

        css_markers = (
            ".mpm-view-switcher",
            ".mpm-shell",
            ".mpm-stage",
            ".mpm-feature-label",
            ".mpm-restriction-label",
            ".mpm-restriction-leader",
        )

        for marker in css_markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.css,
                )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularPlasmidMapTemplateTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username=(
                    "detailed-map-owner-v2"
                ),
                password="test-password",
            )
        )

        self.molecule = (
            MolecularSequence
            .objects
            .create(
                name=(
                    "Detailed interactive "
                    "map QA"
                ),
                sequence_type="plasmid",
                topology="circular",
                sequence=(
                    "ATGCGTACGT"
                    "GAATTC"
                    "CGTACGATCG"
                    "GGATCC"
                    "TACGATCGAT"
                    "CTCGAG"
                    "GCTAGC"
                    "ATCGATCGAT"
                    "AAGCTT"
                    "CGATCGATCG"
                ),
                owner=self.user,
            )
        )

        MolecularFeature.objects.create(
            molecule=self.molecule,
            name="Reporter CDS",
            feature_type="cds",
            start=4,
            end=32,
            strand="+",
            color="#4F46E5",
            order=0,
        )

        self.client.force_login(
            self.user
        )

    def test_detail_page_exposes_detailed_map_assets_and_api(
        self,
    ):
        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                args=[
                    self.molecule.id,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        markers = (
            "data-restriction-sites-url=",
            "data-csrf-token=",
            (
                "molecular_plasmid_map.css"
                "?v=20260810-final-ux-v2"
            ),
            (
                "molecular_plasmid_map.js"
                "?v=20260810-final-ux-v2"
            ),
        )

        for marker in markers:
            with self.subTest(
                marker=marker,
            ):
                self.assertContains(
                    response,
                    marker,
                )
