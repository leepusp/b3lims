from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_script_prefix
from django.urls import reverse

from core.models.samples.origin import SampleOrigin
from core.models.samples.sample import Sample


class SampleOriginDistributionMapTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="distributionowner",
            password="test-password",
        )

        self.other = User.objects.create_user(
            username="distributionother",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="DIST-MAP-001",
            sample_type="Bacterium (Host)",
            organism_name="Marine test bacterium",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
        )

        SampleOrigin.objects.create(
            sample=self.sample,
            collection_site_name="South Atlantic Station",
            geo_loc_name="South Atlantic",
            country_or_ocean="Atlantic Ocean",
            latitude=Decimal("-28.224100"),
            longitude=Decimal("-39.887200"),
            depth_m=Decimal("1120.000"),
            habitat="Marine",
            environmental_medium="Ocean water",
            env_broad_scale="Marine biome",
            env_local_scale="Open ocean",
            location_visibility="internal",
        )

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        )

        if prefix and url.startswith(prefix):
            return (
                url[len(prefix):]
                or "/"
            )

        return url

    def get_route(self, user):
        self.client.force_login(
            user
        )

        return self.client.get(
            self.client_path(
                reverse(
                    "samples_origin_map"
                )
            )
        )

    def test_owner_sees_dedicated_distribution_map(self):
        response = self.get_route(
            self.owner
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "internal/samples/origin_map.html",
        )

        self.assertContains(
            response,
            "Sample Origin Map",
        )

        self.assertContains(
            response,
            "Interactive Distribution Map",
        )

        self.assertContains(
            response,
            "data-sample-origin-dashboard",
        )

        for element_id in (
            "sample-origin-filter-search",
            "sample-origin-filter-type",
            "sample-origin-filter-status",
            "sample-origin-filter-biobank",
            "sample-origin-filter-group",
            "sample-origin-filter-broad-scale",
            "sample-origin-filter-habitat",
            "sample-origin-filter-environment",
            "sample-origin-filter-local-scale",
            "sample-origin-filter-location",
            "sample-origin-filter-site",
            "sample-origin-filter-reset",
        ):
            self.assertContains(
                response,
                element_id,
            )

        points = response.context[
            "sample_origin_points"
        ]

        self.assertEqual(
            len(points),
            1,
        )

        self.assertEqual(
            points[0]["sample_id"],
            "DIST-MAP-001",
        )

        self.assertEqual(
            points[0]["country_or_ocean"],
            "Atlantic Ocean",
        )

    def test_private_origin_is_not_exposed_to_other_user(self):
        response = self.get_route(
            self.other
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.context[
                "sample_origin_points"
            ],
            [],
        )

        self.assertNotContains(
            response,
            "DIST-MAP-001",
        )

        self.assertContains(
            response,
            "data-sample-origin-dashboard",
        )

    def test_dedicated_map_route_has_expected_prefix(self):
        with override_script_prefix(
            "/c3-lims/"
        ):
            route = reverse(
                "samples_origin_map"
            )

        self.assertEqual(
            route,
            "/c3-lims/samples/map/",
        )
