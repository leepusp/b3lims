from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Sample
from core.models.samples.origin import (
    SampleOrigin,
)
from core.services.public_catalog import (
    public_geographic_distribution,
    public_home_context,
    public_organism_sample_type_network,
)


class PublicHomeV33Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username="V33-OWNER",
        )

        cls.public_one = Sample.objects.create(
            sample_id="V33-PUBLIC-001",
            sample_type="Bacterium",
            organism_name="Public organism alpha",
            owner=cls.owner,
            is_public=True,
            is_embargoed=False,
            is_active=True,
        )

        cls.public_two = Sample.objects.create(
            sample_id="V33-PUBLIC-002",
            sample_type="Bacterium",
            organism_name="Public organism alpha",
            owner=cls.owner,
            is_public=True,
            is_embargoed=False,
            is_active=True,
        )

        cls.public_internal_origin = (
            Sample.objects.create(
                sample_id="V33-PUBLIC-003",
                sample_type="Phage",
                organism_name="Public organism beta",
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.private_sample = Sample.objects.create(
            sample_id="V33-PRIVATE-SENTINEL",
            sample_type="PRIVATE-TYPE-SENTINEL",
            organism_name="PRIVATE-ORGANISM-SENTINEL",
            owner=cls.owner,
            is_public=False,
            is_embargoed=False,
            is_active=True,
        )

        cls.embargoed_sample = (
            Sample.objects.create(
                sample_id="V33-EMBARGO-SENTINEL",
                sample_type="EMBARGO-TYPE-SENTINEL",
                organism_name="EMBARGO-ORGANISM-SENTINEL",
                owner=cls.owner,
                is_public=True,
                is_embargoed=True,
                is_active=True,
            )
        )


        cls._origin(
            cls.public_one,
            "Brazil",
            SampleOrigin.LOCATION_APPROXIMATE,
            Decimal("-23.550520"),
            Decimal("-46.633308"),
        )

        cls._origin(
            cls.public_two,
            "Brazil",
            SampleOrigin.LOCATION_EXACT,
            Decimal("-22.906847"),
            Decimal("-43.172897"),
        )

        cls._origin(
            cls.public_internal_origin,
            "INTERNAL-GEO-SENTINEL",
            SampleOrigin.LOCATION_INTERNAL,
            Decimal("-15.793889"),
            Decimal("-47.882778"),
        )

        cls._origin(
            cls.private_sample,
            "PRIVATE-GEO-SENTINEL",
            SampleOrigin.LOCATION_EXACT,
            Decimal("-12.000000"),
            Decimal("-44.000000"),
        )

        cls._origin(
            cls.embargoed_sample,
            "EMBARGO-GEO-SENTINEL",
            SampleOrigin.LOCATION_APPROXIMATE,
            Decimal("-11.000000"),
            Decimal("-43.000000"),
        )

    @classmethod
    def _origin(
        cls,
        sample,
        location,
        visibility,
        latitude,
        longitude,
    ):
        SampleOrigin.objects.create(
            sample=sample,
            collection_site_name=(
                "V3.3 test site"
            ),
            geo_loc_name=location,
            country_or_ocean=location,
            latitude=latitude,
            longitude=longitude,
            habitat="Test habitat",
            environmental_medium=(
                "Test medium"
            ),
            location_visibility=visibility,
        )

    def test_geography_uses_public_visibility_boundary(
        self,
    ):
        self.assertEqual(
            public_geographic_distribution(),
            [
                {
                    "location": "Brazil",
                    "total": 2,
                }
            ],
        )

    def test_internal_location_does_not_enter_map_payload(
        self,
    ):
        locations = {
            row["location"]
            for row in (
                public_geographic_distribution()
            )
        }

        self.assertNotIn(
            "INTERNAL-GEO-SENTINEL",
            locations,
        )

    def test_private_and_embargoed_locations_do_not_enter_map_payload(
        self,
    ):
        locations = {
            row["location"]
            for row in (
                public_geographic_distribution()
            )
        }

        self.assertNotIn(
            "PRIVATE-GEO-SENTINEL",
            locations,
        )

        self.assertNotIn(
            "EMBARGO-GEO-SENTINEL",
            locations,
        )

    def test_geographic_payload_has_no_coordinates(
        self,
    ):
        rows = (
            public_geographic_distribution()
        )

        for row in rows:
            self.assertEqual(
                set(
                    row
                ),
                {
                    "location",
                    "total",
                },
            )

    def test_network_uses_public_samples_only(
        self,
    ):
        rows = (
            public_organism_sample_type_network()
        )

        self.assertEqual(
            rows,
            [
                {
                    "organism_name": (
                        "Public organism alpha"
                    ),
                    "sample_type": "Bacterium",
                    "total": 2,
                },
                {
                    "organism_name": (
                        "Public organism beta"
                    ),
                    "sample_type": "Phage",
                    "total": 1,
                },
            ],
        )

    def test_private_network_metadata_is_excluded(
        self,
    ):
        serialized = repr(
            public_organism_sample_type_network()
        )

        for sentinel in (
            "PRIVATE-TYPE-SENTINEL",
            "PRIVATE-ORGANISM-SENTINEL",
            "EMBARGO-TYPE-SENTINEL",
            "EMBARGO-ORGANISM-SENTINEL",
        ):
            self.assertNotIn(
                sentinel,
                serialized,
            )

    def test_home_context_contains_new_safe_views(
        self,
    ):
        context = (
            public_home_context()
        )

        self.assertIn(
            "geographic_distribution",
            context,
        )

        self.assertIn(
            "organism_sample_type_network",
            context,
        )

    def test_home_uses_fluid_wide_layout(
        self,
    ):
        base = Path(
            "core/interfaces/public/base.html"
        ).read_text()

        home = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        self.assertIn(
            "{% block main_class %}",
            base,
        )

        self.assertIn(
            "container-fluid py-4",
            home,
        )

        self.assertIn(
            "max-width: 1720px",
            home,
        )

    def test_microorganism_canvas_reacts_to_pointer(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for token in (
            '"pointermove"',
            '"pointerleave"',
            "translate3d(",
            "scale(1.035)",
            (
                "(prefers-reduced-motion: "
                "reduce)"
            ),
        ):
            self.assertIn(
                token,
                source,
            )

    def test_visualization_tabs_exist(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for token in (
            "publicViewOverviewTab",
            "publicViewGeographyTab",
            "publicViewNetworkTab",
            "publicViewRankingTab",
            "publicViewBubbleTab",
            "Overview",
            "Geography",
            "Network",
            "Rankings",
            "Bubbles",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_new_payloads_use_json_script(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        self.assertIn(
            (
                "geographic_distribution"
                '|json_script:'
                '"public-geographic-data"'
            ),
            source,
        )

        self.assertIn(
            (
                "organism_sample_type_network"
                '|json_script:'
                '"public-network-data"'
            ),
            source,
        )

    def test_world_map_dependency_is_pinned(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        self.assertIn(
            (
                "echarts-maps@1.1.0/"
                "world.js"
            ),
            source,
        )

    def test_new_charts_do_not_fetch_public_data(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

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

    def test_home_does_not_render_hidden_geography(
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

        for sentinel in (
            "INTERNAL-GEO-SENTINEL",
            "PRIVATE-GEO-SENTINEL",
            "EMBARGO-GEO-SENTINEL",
            "PRIVATE-ORGANISM-SENTINEL",
            "EMBARGO-ORGANISM-SENTINEL",
        ):
            self.assertNotContains(
                response,
                sentinel,
            )

        self.assertContains(
            response,
            "Brazil",
        )

        self.assertContains(
            response,
            "Organism ↔ Sample type network",
        )
