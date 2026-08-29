from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
)


class WorkspaceV2Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.user = User.objects.create_user(
            username="workspace-v2-user",
            first_name="Workspace",
        )

        cls.other_user = (
            User.objects.create_user(
                username=(
                    "workspace-v2-other"
                ),
            )
        )

        cls.visible_collection = (
            Collection.objects.create(
                name=(
                    "Workspace Visible Collection"
                ),
                owner=cls.user,
                is_active=True,
                is_public=False,
            )
        )

        cls.hidden_collection = (
            Collection.objects.create(
                name=(
                    "WORKSPACE-HIDDEN-COLLECTION"
                ),
                owner=cls.other_user,
                is_active=True,
                is_public=False,
            )
        )

        cls.visible_sample = (
            Sample.objects.create(
                sample_id=(
                    "WORKSPACE-VISIBLE-SAMPLE"
                ),
                sample_type=(
                    "Bacterium (Host)"
                ),
                organism_name=(
                    "Workspace visible organism"
                ),
                owner=cls.user,
                is_active=True,
                is_public=False,
            )
        )

        cls.hidden_sample = (
            Sample.objects.create(
                sample_id=(
                    "WORKSPACE-HIDDEN-SAMPLE"
                ),
                sample_type=(
                    "Hidden type"
                ),
                organism_name=(
                    "WORKSPACE-HIDDEN-ORGANISM"
                ),
                owner=cls.other_user,
                is_active=True,
                is_public=False,
            )
        )


    def setUp(
        self,
    ):
        self.client.force_login(
            self.user
        )


    def test_workspace_renders_scientific_research_hub(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for text in (
            "Scientific Research Workspace",
            "My Research",
            "Scientific Context",
            "Analysis & Compute",
            "Recent Activity",
            "Quick Actions",
        ):
            self.assertContains(
                response,
                text,
                html=False,
            )


    def test_workspace_counts_and_recent_resources_are_user_scoped(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        self.assertEqual(
            response.context[
                "stats"
            ][
                "total_samples"
            ],
            1,
        )

        self.assertEqual(
            response.context[
                "stats"
            ][
                "total_collections"
            ],
            1,
        )

        self.assertContains(
            response,
            "WORKSPACE-VISIBLE-SAMPLE",
        )

        self.assertContains(
            response,
            "Workspace Visible Collection",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-SAMPLE",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-ORGANISM",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-COLLECTION",
        )


    def test_workspace_preserves_legacy_stats_contract(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        stats = response.context[
            "stats"
        ]

        for key in (
            "total_samples",
            "pending_qc",
            "new_samples_30d",
            "total_collections",
            "recent_activity",
            "chart_labels",
            "chart_data",
        ):
            self.assertIn(
                key,
                stats,
            )


    def test_workspace_v2_uses_existing_scientific_tools(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        for url_name in (
            "notebook_index",
            "jupyter_index",
            "molecular_registry_index",
            "samples_network",
            "samples_origin_map",
        ):
            self.assertContains(
                response,
                reverse(
                    url_name
                ),
            )


    def test_workspace_template_has_no_chart_js_or_inline_style_block(
        self,
    ):
        source = Path(
            "core/interfaces/internal/"
            "workspace/workspace.html"
        ).read_text()

        self.assertIn(
            (
                "internal/workspace/"
                "workspace.css"
            ),
            source,
        )

        self.assertNotIn(
            "chart.js",
            source.lower(),
        )

        self.assertNotIn(
            "<canvas",
            source.lower(),
        )

        self.assertNotIn(
            "<style",
            source.lower(),
        )

        self.assertNotIn(
            "<script",
            source.lower(),
        )


    def test_workspace_view_preserves_authorization_helpers(
        self,
    ):
        source = Path(
            "core/views/internal/"
            "workspace/views.py"
        ).read_text()

        for helper in (
            "visible_workspace_samples_for_user",
            "visible_workspace_collections_for_user",
            "visible_workspace_events_for_user",
            "research_group_ids_for_user",
        ):
            self.assertIn(
                helper,
                source,
            )

        self.assertIn(
            "_scientific_evidence_summary",
            source,
        )


    def test_workspace_does_not_introduce_analysis_models(
        self,
    ):
        source = (
            Path(
                "core/views/internal/"
                "workspace/views.py"
            ).read_text()
            +
            Path(
                "core/interfaces/internal/"
                "workspace/workspace.html"
            ).read_text()
        )

        for forbidden in (
            "AnalysisRun",
            "ComputeJob",
            "AnalysisProject",
            "AnalysisWorkflow",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )
