from pathlib import Path

from django.test import SimpleTestCase


class PublicHomeV351RecoveryTests(
    SimpleTestCase
):
    @staticmethod
    def source():
        return Path(
            "core/interfaces/public/index.html"
        ).read_text()


    def test_external_chart_scripts_are_not_parser_blocking(
        self,
    ):
        source = self.source()


        self.assertNotIn(
            (
                '<script\n'
                '    src="https://cdn.jsdelivr.net/'
                'npm/echarts@5.5.1/dist/echarts.min.js">'
            ),
            source,
        )


        self.assertNotIn(
            (
                '<script\n'
                '    src="https://cdn.jsdelivr.net/'
                'npm/echarts-maps@1.1.0/world.js">'
            ),
            source,
        )


    def test_chart_dependencies_use_dynamic_async_loader(
        self,
    ):
        source = self.source()


        for token in (
            "B3LimsChartLoader",
            "document.createElement(",
            'script.async = true',
            "whenEChartsReady",
            "whenWorldMapReady",
            "LOAD_TIMEOUT_MS = 8000",
        ):
            self.assertIn(
                token,
                source,
            )


    def test_hero_animation_is_independent_from_chart_download(
        self,
    ):
        source = self.source()


        hero_position = source.index(
            "Decorative biological hero animation"
        )

        overview_wait_position = source.index(
            "initializePublicChartsWhenReady"
        )


        self.assertLess(
            hero_position,
            overview_wait_position,
        )


        for token in (
            "requestAnimationFrame",
            "applyPointerInteraction",
            'id="microbes"',
        ):
            self.assertIn(
                token,
                source,
            )


    def test_overview_has_visible_dependency_failure_state(
        self,
    ):
        source = self.source()


        for token in (
            "showOverviewDependencyFallback",
            (
                "Sample type composition is temporarily "
            ),
            (
                "Organism representation is temporarily "
            ),
        ):
            self.assertIn(
                token,
                source,
            )


    def test_world_map_is_loaded_only_through_geography_dependency(
        self,
    ):
        source = self.source()


        self.assertIn(
            "loader.whenWorldMapReady()",
            source,
        )


        self.assertIn(
            (
                "npm/echarts-maps@1.1.0/"
                "world.js"
            ),
            source,
        )


    def test_advanced_explorers_remain_lazy(
        self,
    ):
        source = self.source()


        for token in (
            "initializeResolvedView",
            "activateView",
            "loader.whenEChartsReady()",
            "loader.whenWorldMapReady()",
        ):
            self.assertIn(
                token,
                source,
            )


        for view_name in (
            "network",
            "ranking",
            "sankey",
        ):
            self.assertRegex(
                source,
                (
                    r"viewName"
                    r"\s*"
                    r"==="
                    r"\s*"
                    r'"'
                    +
                    view_name
                    +
                    r'"'
                ),
            )


        self.assertRegex(
            source,
            (
                r"viewName"
                r"\s*"
                r"==="
                r"\s*"
                r'"geography"'
                r"\s*"
                r"\?"
                r"\s*"
                r"loader\.whenWorldMapReady\(\)"
                r"\s*"
                r":"
                r"\s*"
                r"loader\.whenEChartsReady\(\)"
            ),
        )

    def test_synthetic_resize_dispatch_is_removed(
        self,
    ):
        source = self.source()


        self.assertNotIn(
            "window.dispatchEvent(",
            source,
        )


    def test_v35_features_are_preserved(
        self,
    ):
        source = self.source()


        for token in (
            "publicNetworkSearch",
            "publicNetworkSampleType",
            "publicNetworkMinimum",
            "publicNetworkLayout",
            "publicNetworkLabels",
            "publicRankingRank",
            "publicRankingStyle",
            "publicRankingDetails",
            "publicViewSankeyTab",
            'type: "sankey"',
        ):
            self.assertIn(
                token,
                source,
            )


    def test_bubbles_remain_removed(
        self,
    ):
        source = self.source()


        for forbidden in (
            "publicViewBubbleTab",
            "publicBubbleChart",
            "initializeBubbleMatrix",
            'type: "scatter"',
        ):
            self.assertNotIn(
                forbidden,
                source,
            )


    def test_public_explorer_still_has_no_data_fetch_api(
        self,
    ):
        source = self.source()


        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "$.ajax",
            "/public/api/",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )
