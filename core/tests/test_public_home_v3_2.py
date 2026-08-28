from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class PublicHomeV32PrototypeIntegrationTests(
    TestCase
):
    def template_source(
        self,
    ):
        return Path(
            "core/interfaces/public/index.html"
        ).read_text()

    def base_source(
        self,
    ):
        return Path(
            "core/interfaces/public/base.html"
        ).read_text()

    def test_inter_typography_is_loaded(
        self,
    ):
        source = self.base_source()

        self.assertIn(
            "fonts.googleapis.com",
            source,
        )

        self.assertIn(
            (
                "family=Inter:"
                "wght@400;500;600;700;800"
            ),
            source,
        )

        self.assertIn(
            '"Inter"',
            source,
        )

    def test_prototype_design_tokens_are_available(
        self,
    ):
        source = self.base_source()

        self.assertIn(
            "--b3-radius: 16px",
            source,
        )

        self.assertIn(
            "--b3-shadow:",
            source,
        )

    def test_scientific_hero_contains_decorative_canvas(
        self,
    ):
        source = self.template_source()

        self.assertIn(
            'id="microbes"',
            source,
        )

        self.assertIn(
            'aria-hidden="true"',
            source,
        )

        for token in (
            "drawBacillus",
            "drawCoccus",
            "drawSpirillum",
            "drawPhage",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_hero_respects_reduced_motion(
        self,
    ):
        source = self.template_source()

        self.assertIn(
            (
                "(prefers-reduced-motion: "
                "reduce)"
            ),
            source,
        )

        self.assertIn(
            "reducedMotion",
            source,
        )

    def test_prototype_navigation_uses_real_routes(
        self,
    ):
        source = self.template_source()

        for route_name in (
            "public_collections",
            "public_about",
            "public_governance",
            "public_shipments_portal",
            "login",
        ):
            self.assertIn(
                (
                    "{% url '"
                    + route_name
                    + "' %}"
                ),
                source,
            )

    def test_metrics_use_real_public_context(
        self,
    ):
        source = self.template_source()

        for token in (
            "{{ public_metrics.public_samples }}",
            "{{ public_metrics.public_collections }}",
            "{{ public_metrics.organisms }}",
            "{{ public_metrics.geographic_origins }}",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_prototype_demo_values_are_not_imported(
        self,
    ):
        source = self.template_source()

        for forbidden in (
            "356,247",
            "1,684",
            "2,193",
            "248",
            "37 countries with sample records",
            "Plants",
            "Invertebrates",
            "Global coverage",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

    def test_illustrative_map_is_not_imported(
        self,
    ):
        source = self.template_source()

        for forbidden in (
            'class="map-svg"',
            "Geographic coverage",
            "density blobs",
            "Brazil highlighted",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

    def test_existing_real_charts_are_preserved(
        self,
    ):
        source = self.template_source()

        for token in (
            'json_script:"public-sample-type-data"',
            'json_script:"public-organism-data"',
            "echarts@5.5.1/dist/echarts.min.js",
            'type: "pie"',
            'type: "treemap"',
            "publicSampleTypeChart",
            "publicOrganismChart",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_decorative_canvas_has_no_network_access(
        self,
    ):
        source = self.template_source()

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

    def test_public_home_renders_prototype_composition(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for token in (
            "Welcome to the B3 LIMS public catalog",
            "B3 LIMS at a glance",
            "Catalog at a glance",
            "Public catalog exploration",
            "Sample type composition",
            "Organism representation",
            "Explore and understand the catalog",
            "Scientific exploration",
            "Resources and governance",
        ):
            self.assertContains(
                response,
                token,
            )

    def test_home_remains_english(
        self,
    ):
        source = self.template_source()

        for forbidden in (
            "Catálogo",
            "Coleções",
            "Buscar",
            "Governança",
            "Remessas",
            "Área interna",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )
