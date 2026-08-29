from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
)


class WorkspaceV22Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.user = User.objects.create_user(
            username="workspace-v22-user",
            first_name="Workspace",
        )

        cls.other_user = (
            User.objects.create_user(
                username="workspace-v22-other",
            )
        )

        cls.visible_collection = (
            Collection.objects.create(
                name="Workspace Visible Collection",
                owner=cls.user,
                is_active=True,
                is_public=False,
            )
        )

        cls.hidden_collection = (
            Collection.objects.create(
                name="WORKSPACE-HIDDEN-COLLECTION",
                owner=cls.other_user,
                is_active=True,
                is_public=False,
            )
        )

        cls.visible_sample = (
            Sample.objects.create(
                sample_id="WORKSPACE-VISIBLE-SAMPLE",
                sample_type="Bacterium (Host)",
                organism_name="Workspace visible organism",
                owner=cls.user,
                is_active=True,
                is_public=False,
            )
        )

        cls.hidden_sample = (
            Sample.objects.create(
                sample_id="WORKSPACE-HIDDEN-SAMPLE",
                sample_type="Hidden type",
                organism_name="WORKSPACE-HIDDEN-ORGANISM",
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


    def test_workspace_renders_compact_scientific_dashboard(
        self,
    ):
        response = self.client.get(
            reverse("workspace")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for text in (
            "Welcome back,",
            "Total Samples",
            "Pending QC",
            "New (30d)",
            "Collections",
            "Sample Types Distribution",
            "Scientific Evidence",
            "Recent Samples",
            "Recent Collections",
            "Quick Actions",
            "Analysis & Compute",
            "Recent Activity",
        ):
            self.assertContains(
                response,
                text,
            )


    def test_workspace_resources_remain_user_scoped(
        self,
    ):
        response = self.client.get(
            reverse("workspace")
        )

        self.assertEqual(
            response.context["stats"]["total_samples"],
            1,
        )

        self.assertEqual(
            response.context["stats"]["total_collections"],
            1,
        )

        self.assertContains(
            response,
            "WORKSPACE-VISIBLE-SAMPLE",
        )

        self.assertContains(
            response,
            "Workspace visible organism",
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


    def test_workspace_preserves_v21_context_contract(
        self,
    ):
        response = self.client.get(
            reverse("workspace")
        )

        stats = response.context["stats"]

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

        workspace_v2 = response.context[
            "workspace_v2"
        ]

        for key in (
            "research_groups",
            "recent_samples",
            "recent_collections",
            "sample_type_distribution",
            "evidence",
            "scope_mode",
        ):
            self.assertIn(
                key,
                workspace_v2,
            )


    def test_workspace_uses_existing_scientific_routes(
        self,
    ):
        response = self.client.get(
            reverse("workspace")
        )

        for url_name in (
            "samples_list",
            "collections_list",
            "sample_add",
            "collection_create",
            "samples_import",
            "notebook_create",
            "notebook_index",
            "jupyter_index",
            "molecular_registry_index",
            "samples_network",
            "samples_origin_map",
            "lab_calendar",
        ):
            self.assertContains(
                response,
                reverse(url_name),
            )


    def test_workspace_returns_to_compact_card_structure(
        self,
    ):
        template = Path(
            "core/interfaces/internal/"
            "workspace/workspace.html"
        ).read_text()

        css = Path(
            "core/static/internal/"
            "workspace/workspace.css"
        ).read_text()

        for token in (
            'class="workspace"',
            "workspace-kpis",
            "workspace-grid",
            "workspace-main",
            "workspace-sidebar",
            "workspace-card",
            "workspace-overview-grid",
            "workspace-distribution",
        ):
            self.assertIn(
                token,
                template,
            )

        self.assertIn(
            (
                "grid-template-columns: "
                "minmax(0, 1fr) 320px;"
            ),
            css,
        )

        self.assertNotIn(
            "workspace-hero",
            template,
        )

        self.assertNotIn(
            "research-workspace",
            template,
        )


    def test_workspace_frontend_has_no_blocking_chart_dependency(
        self,
    ):
        template = Path(
            "core/interfaces/internal/"
            "workspace/workspace.html"
        ).read_text()

        self.assertIn(
            (
                "internal/workspace/"
                "workspace.css"
            ),
            template,
        )

        for forbidden in (
            "chart.js",
            "<canvas",
            "<script",
            "<style",
        ):
            self.assertNotIn(
                forbidden,
                template.lower(),
            )


    def test_workspace_preserves_authorization_and_no_fake_analysis_models(
        self,
    ):
        view = Path(
            "core/views/internal/"
            "workspace/views.py"
        ).read_text()

        template = Path(
            "core/interfaces/internal/"
            "workspace/workspace.html"
        ).read_text()

        for helper in (
            "visible_workspace_samples_for_user",
            "visible_workspace_collections_for_user",
            "visible_workspace_events_for_user",
            "research_group_ids_for_user",
        ):
            self.assertIn(
                helper,
                view,
            )

        for forbidden in (
            "AnalysisRun",
            "ComputeJob",
            "AnalysisProject",
            "AnalysisWorkflow",
        ):
            self.assertNotIn(
                forbidden,
                view + template,
            )
