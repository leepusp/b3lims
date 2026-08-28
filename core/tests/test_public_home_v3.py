from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
)
from core.services.public_catalog import (
    public_home_context,
    public_organism_distribution,
)


class PublicHomeV3Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username=(
                "PRIVATE-PORTAL-OWNER-SENTINEL"
            ),
        )

        cls.public_collection = (
            Collection.objects.create(
                name="Portal Public Collection",
                description=(
                    "Public Collection used by the "
                    "portal interface regression test."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.public_sample_one = (
            Sample.objects.create(
                sample_id="PORTAL-PUBLIC-001",
                sample_type="Bacteria",
                organism_name=(
                    "Pseudomonas portalensis"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.public_sample_two = (
            Sample.objects.create(
                sample_id="PORTAL-PUBLIC-002",
                sample_type="Bacteria",
                organism_name=(
                    "Pseudomonas portalensis"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.public_sample_three = (
            Sample.objects.create(
                sample_id="PORTAL-PUBLIC-003",
                sample_type="Bacteriophage",
                organism_name=(
                    "Public phage organism"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.private_sample = (
            Sample.objects.create(
                sample_id=(
                    "PRIVATE-PORTAL-SAMPLE-SENTINEL"
                ),
                sample_type=(
                    "PRIVATE-PORTAL-TYPE-SENTINEL"
                ),
                organism_name=(
                    "PRIVATE-PORTAL-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=False,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.embargoed_sample = (
            Sample.objects.create(
                sample_id=(
                    "EMBARGOED-PORTAL-SAMPLE-SENTINEL"
                ),
                sample_type=(
                    "EMBARGOED-PORTAL-TYPE-SENTINEL"
                ),
                organism_name=(
                    "EMBARGOED-PORTAL-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=True,
                is_active=True,
            )
        )

        cls.public_collection.samples.add(
            cls.public_sample_one,
            cls.public_sample_two,
            cls.public_sample_three,
            cls.private_sample,
            cls.embargoed_sample,
        )

    def test_public_organism_distribution_uses_public_samples_only(
        self,
    ):
        rows = (
            public_organism_distribution()
        )

        self.assertEqual(
            rows,
            [
                {
                    "organism_name": (
                        "Pseudomonas portalensis"
                    ),
                    "total": 2,
                },
                {
                    "organism_name": (
                        "Public phage organism"
                    ),
                    "total": 1,
                },
            ],
        )

    def test_private_organism_cannot_enter_public_distribution(
        self,
    ):
        names = {
            row[
                "organism_name"
            ]
            for row in (
                public_organism_distribution()
            )
        }

        self.assertNotIn(
            (
                "PRIVATE-PORTAL-"
                "ORGANISM-SENTINEL"
            ),
            names,
        )

    def test_embargoed_organism_cannot_enter_public_distribution(
        self,
    ):
        names = {
            row[
                "organism_name"
            ]
            for row in (
                public_organism_distribution()
            )
        }

        self.assertNotIn(
            (
                "EMBARGOED-PORTAL-"
                "ORGANISM-SENTINEL"
            ),
            names,
        )

    def test_public_home_context_includes_organism_distribution(
        self,
    ):
        context = (
            public_home_context()
        )

        self.assertIn(
            "organism_distribution",
            context,
        )

        self.assertEqual(
            sum(
                row["total"]
                for row in context[
                    "organism_distribution"
                ]
            ),
            3,
        )

    def test_public_home_renders_portal_structure(
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
            (
                "Welcome to the B3 "
                "Biobank public catalog"
            ),
            "Public Biobank resources",
            (
                "Explore and understand "
                "the catalog"
            ),
            "Catalog at a glance",
            "Interactive data views",
            "Sample type composition",
            "Organism representation",
            "Scientific exploration",
            "Resources and governance",
        ):
            self.assertContains(
                response,
                token,
            )

    def test_public_home_renders_existing_gateway_routes(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        for route_name in (
            "public_collections",
            "public_about",
            "public_governance",
            "public_shipments_portal",
        ):
            self.assertContains(
                response,
                reverse(
                    route_name
                ),
            )

    def test_public_home_does_not_render_private_organism_metadata(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        for sentinel in (
            (
                "PRIVATE-PORTAL-"
                "ORGANISM-SENTINEL"
            ),
            (
                "EMBARGOED-PORTAL-"
                "ORGANISM-SENTINEL"
            ),
            (
                "PRIVATE-PORTAL-"
                "TYPE-SENTINEL"
            ),
            (
                "EMBARGOED-PORTAL-"
                "TYPE-SENTINEL"
            ),
        ):
            self.assertNotContains(
                response,
                sentinel,
            )

    def test_template_uses_json_script_not_unsafe_direct_json(
        self,
    ):
        template = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        self.assertIn(
            (
                'sample_type_distribution'
                '|json_script:'
                '"public-sample-type-data"'
            ),
            template,
        )

        self.assertIn(
            (
                'organism_distribution'
                '|json_script:'
                '"public-organism-data"'
            ),
            template,
        )

        self.assertNotIn(
            "|safe",
            template,
        )

    def test_template_uses_interactive_donut_and_treemap(
        self,
    ):
        template = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for token in (
            (
                "echarts@5.5.1/"
                "dist/echarts.min.js"
            ),
            "window.echarts.init",
            'type: "pie"',
            'type: "treemap"',
            "publicSampleTypeChart",
            "publicOrganismChart",
            'renderMode: "richText"',
        ):
            self.assertIn(
                token,
                template,
            )

    def test_interactive_charts_do_not_create_public_api_dependency(
        self,
    ):
        template = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for forbidden in (
            "/public/api/",
            "fetch(",
            "XMLHttpRequest",
            "$.ajax",
        ):
            self.assertNotIn(
                forbidden,
                template,
            )

    def test_v2_progress_bars_are_removed(
        self,
    ):
        template = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for forbidden in (
            "composition-track",
            "composition-fill",
            'role="progressbar"',
        ):
            self.assertNotIn(
                forbidden,
                template,
            )

    def test_template_does_not_traverse_sensitive_relations(
        self,
    ):
        template = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for forbidden in (
            "collection.owner",
            "collection.research_group",
            "collection.biobank",
            "collection.samples.",
            "collection.tags.all",
            "collection.tags.exists",
            "sample.owner",
            "storage_location",
            "micro_qr_token",
            "scientific_notes",
        ):
            self.assertNotIn(
                forbidden,
                template,
            )

    def test_organism_distribution_starts_from_public_projection(
        self,
    ):
        source = Path(
            "core/services/public_catalog.py"
        ).read_text()

        start = source.index(
            "def public_organism_distribution("
        )

        end = source.index(
            "def featured_public_collections(",
            start,
        )

        block = source[
            start:end
        ]

        self.assertIn(
            "public_samples_queryset()",
            block,
        )

        self.assertNotIn(
            "Sample.objects",
            block,
        )

        self.assertNotIn(
            "Collection.objects",
            block,
        )
