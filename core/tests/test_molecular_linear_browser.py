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
    )


class MolecularLinearBrowserStaticTests(
    SimpleTestCase
):
    def setUp(self):
        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        self.js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_linear_browser.js'
        ).read_text(
            encoding="utf-8"
        )

        self.css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_linear_browser.css'
        ).read_text(
            encoding="utf-8"
        )

    def test_browser_is_third_workspace_view(
        self,
    ):
        for marker in (
            "Linear browser",
            'data-mpm-view',
            '"linear"',
            "showLinearBrowser",
            "mw-linear-browser",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_wrapped_and_continuous_modes_exist(
        self,
    ):
        for marker in (
            'value="wrapped"',
            'value="continuous"',
            "Bases / row",
            "autoBasesPerRow",
            "renderRow",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_feature_interaction_uses_shared_workspace(
        self,
    ):
        for marker in (
            "window",
            "BiobankMolecularWorkspace",
            "selectFeature",
            "selectedFeature",
            "biobank:molecular-workspace-change",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_browser_supports_strands_labels_and_search(
        self,
    ):
        for marker in (
            "Separate strands",
            "Feature labels",
            "Find feature",
            "assignFragmentLanes",
            "featureMatches",
            "is-search-match",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_restriction_ticks_are_optional_and_interactive(
        self,
    ):
        for marker in (
            "Restriction ticks",
            "restrictionSitesUrl",
            "minimum_site_length",
            '"unique"',
            "selectSequenceRange",
            "mlb-restriction-tick",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_css_contains_browser_structure(
        self,
    ):
        for marker in (
            ".mlb-shell",
            ".mlb-toolbar",
            ".mlb-overview-wrap",
            ".mlb-stage",
            ".mlb-feature",
            ".mlb-feature-label",
            ".mlb-restriction-tick",
        ):
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
class MolecularLinearBrowserTemplateTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username=(
                    "linear-browser-owner"
                ),
                password="test-password",
            )
        )

        self.molecule = (
            MolecularSequence
            .objects
            .create(
                name=(
                    "Linear browser QA plasmid"
                ),
                sequence_type="plasmid",
                topology="circular",
                sequence=(
                    "ATGC"
                    * 1000
                ),
                owner=self.user,
            )
        )

        MolecularFeature.objects.create(
            molecule=self.molecule,
            name="Test CDS",
            feature_type="cds",
            start=200,
            end=1200,
            strand="+",
            color="#4F46E5",
            order=0,
        )

        MolecularFeature.objects.create(
            molecule=self.molecule,
            name="Reverse feature",
            feature_type="promoter",
            start=1700,
            end=2200,
            strand="-",
            color="#E5484D",
            order=1,
        )

        self.client.force_login(
            self.user
        )

    def test_detail_page_loads_linear_browser_assets(
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

        for marker in (
            "molecular_plasmid_layout.css",
            "molecular_plasmid_layout.js",
            "molecular_linear_browser.css",
            "molecular_linear_browser.js",
            (
                "20260807-"
                "molecular-layout-browser-v1"
            ),
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertContains(
                    response,
                    marker,
                )
