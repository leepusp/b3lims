from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
)


class WorkspaceV23Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.user = (
            User.objects.create_user(
                username="workspace-v23-user",
                first_name="Workspace",
            )
        )

        cls.other_user = (
            User.objects.create_user(
                username="workspace-v23-other",
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
                organism_name=(
                    "Workspace visible organism"
                ),
                storage_location=(
                    "Freezer 1 > Shelf 2"
                ),
                owner=cls.user,
                is_active=True,
                is_public=False,
            )
        )

        cls.hidden_sample = (
            Sample.objects.create(
                sample_id="WORKSPACE-HIDDEN-SAMPLE",
                sample_type=(
                    "WORKSPACE-HIDDEN-TYPE"
                ),
                organism_name=(
                    "WORKSPACE-HIDDEN-ORGANISM"
                ),
                storage_location=(
                    "WORKSPACE-HIDDEN-STORAGE"
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


    def test_workspace_renders_v23_dashboard(
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
            "Welcome back,",
            "Register Sample",
            "Create Collection",
            "Import Samples",
            "New Notebook",
            "Samples by type",
            "Samples by storage location",
            "Today's Activity",
            "Scientific Evidence",
            "Taxonomy coverage",
            "Genome coverage",
            "Recent Samples",
            "Recent Collections",
            "Analysis & Compute",
            "Recent Activity",
        ):
            self.assertContains(
                response,
                text,
            )


    def test_workspace_removes_v22_kpi_row_and_profile_duplicate(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        template = Path(
            "core/interfaces/internal/"
            "workspace/workspace.html"
        ).read_text()

        self.assertNotIn(
            "workspace-kpis",
            template,
        )

        self.assertNotContains(
            response,
            "Research profile",
        )

        for old_kpi_label in (
            "Pending QC",
            "New (30d)",
        ):
            self.assertNotContains(
                response,
                old_kpi_label,
            )


    def test_workspace_chart_data_is_authorization_scoped(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        workspace = response.context[
            "workspace_v2"
        ]

        self.assertEqual(
            response.context[
                "stats"
            ][
                "total_samples"
            ],
            1,
        )

        sample_chart = workspace[
            "sample_type_chart"
        ]

        self.assertEqual(
            len(
                sample_chart
            ),
            1,
        )

        self.assertEqual(
            sample_chart[
                0
            ][
                "label"
            ],
            "Bacterium (Host)",
        )

        self.assertEqual(
            sample_chart[
                0
            ][
                "total"
            ],
            1,
        )

        self.assertEqual(
            sample_chart[
                0
            ][
                "percent"
            ],
            100.0,
        )

        storage_chart = workspace[
            "storage_location_chart"
        ]

        self.assertEqual(
            len(
                storage_chart
            ),
            1,
        )

        self.assertEqual(
            storage_chart[
                0
            ][
                "label"
            ],
            "Freezer 1 > Shelf 2",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-TYPE",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-STORAGE",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-SAMPLE",
        )

        self.assertNotContains(
            response,
            "WORKSPACE-HIDDEN-COLLECTION",
        )


    def test_workspace_exposes_real_chart_and_calendar_context(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        workspace = response.context[
            "workspace_v2"
        ]

        for key in (
            "sample_type_chart",
            "storage_location_chart",
            "storage_annotated",
            "today_activity",
        ):
            self.assertIn(
                key,
                workspace,
            )

        self.assertEqual(
            workspace[
                "storage_annotated"
            ],
            1,
        )

        evidence = workspace[
            "evidence"
        ]

        for key in (
            "taxonomy_coverage_percent",
            "taxonomy_coverage_remainder",
            "genome_coverage_percent",
            "genome_coverage_remainder",
        ):
            self.assertIn(
                key,
                evidence,
            )


    def test_workspace_preserves_existing_context_contract(
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

        workspace = response.context[
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
                workspace,
            )


    def test_workspace_uses_existing_routes(
        self,
    ):
        response = self.client.get(
            reverse(
                "workspace"
            )
        )

        for name in (
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
                reverse(
                    name
                ),
            )


    def test_workspace_has_svg_graphs_without_external_chart_runtime(
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
            "workspace-donut",
            "workspace-donut-segment",
            "workspace-bar-chart",
            "workspace-bar-fill",
            "workspace-radial",
            "workspace-calendar-card",
        ):
            self.assertIn(
                token,
                template
                +
                css,
            )

        self.assertGreaterEqual(
            template.count(
                "<svg"
            ),
            3,
        )

        for forbidden in (
            "chart.js",
            "echarts",
            "d3.js",
            "<canvas",
            "<script",
        ):
            self.assertNotIn(
                forbidden,
                template.lower(),
            )


    def test_workspace_preserves_authorization_helpers_and_no_fake_models(
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
                view
                +
                template,
            )
