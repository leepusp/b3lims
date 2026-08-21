from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.origin import SampleOrigin
from core.models.samples.sample import Sample


class SampleOriginMapTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="mapowner",
            password="test-password",
        )

        self.other = user_model.objects.create_user(
            username="mapother",
            password="test-password",
        )

        self.own_sample = Sample.objects.create(
            sample_id="MAP-OWN-001",
            sample_type="Bacterium (Host)",
            organism_name="Marine bacterium",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
        )

        SampleOrigin.objects.create(
            sample=self.own_sample,
            collection_site_name=(
                "South Atlantic Station"
            ),
            country_or_ocean=(
                "Atlantic Ocean"
            ),
            latitude=Decimal(
                "-28.224100"
            ),
            longitude=Decimal(
                "-39.887200"
            ),
            depth_m=Decimal(
                "1120.000"
            ),
            environmental_medium=(
                "Ocean water"
            ),
            location_visibility=(
                "internal"
            ),
        )

        self.public_sample = Sample.objects.create(
            sample_id="MAP-PUBLIC-002",
            sample_type="Phage (Virus)",
            organism_name="Public marine phage",
            owner=self.other,
            status="available",
            is_public=True,
            is_active=True,
        )

        SampleOrigin.objects.create(
            sample=self.public_sample,
            country_or_ocean=(
                "Pacific Ocean"
            ),
            latitude=Decimal(
                "9.838990"
            ),
            longitude=Decimal(
                "-104.290880"
            ),
            depth_m=Decimal(
                "2473.000"
            ),
            environmental_medium=(
                "Ocean water"
            ),
        )

        self.hidden_sample = Sample.objects.create(
            sample_id="MAP-HIDDEN-003",
            sample_type="Plasmid",
            organism_name="Private hidden Sample",
            owner=self.other,
            status="available",
            is_public=False,
            is_active=True,
        )

        SampleOrigin.objects.create(
            sample=self.hidden_sample,
            country_or_ocean="Brazil",
            latitude=Decimal(
                "-23.550520"
            ),
            longitude=Decimal(
                "-46.633308"
            ),
        )

        self.no_coordinates = Sample.objects.create(
            sample_id="MAP-NOCOORD-004",
            sample_type="Other",
            organism_name="Origin without coordinates",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
        )

        SampleOrigin.objects.create(
            sample=self.no_coordinates,
            geo_loc_name=(
                "Unspecified field station"
            ),
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

        if (
            prefix
            and url.startswith(prefix)
        ):
            return (
                url[len(prefix):]
                or "/"
            )

        return url

    def get_as_owner(
        self,
        route_name,
        args=None,
    ):
        self.client.force_login(
            self.owner
        )

        return self.client.get(
            self.client_path(
                reverse(
                    route_name,
                    args=args or [],
                )
            )
        )

    def test_create_renders_origin_fields_and_map(self):
        response = self.get_as_owner(
            "sample_add"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Sample Origin & Collection Site",
        )

        self.assertContains(
            response,
            'name="origin-latitude"',
        )

        self.assertContains(
            response,
            'name="origin-longitude"',
        )

        self.assertContains(
            response,
            "data-sample-origin-map",
        )

    def test_edit_renders_existing_coordinates(self):
        response = self.get_as_owner(
            "sample_edit",
            [
                self.own_sample.pk,
            ],
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "-28.224100",
        )

        self.assertContains(
            response,
            "-39.887200",
        )

        self.assertContains(
            response,
            "Interactive Collection Map",
        )

    def test_detail_renders_readonly_origin_map(self):
        response = self.get_as_owner(
            "sample_detail",
            [
                self.own_sample.pk,
            ],
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "South Atlantic Station",
        )

        self.assertContains(
            response,
            "Atlantic Ocean",
        )

        self.assertContains(
            response,
            "1120.000 m",
        )

        self.assertContains(
            response,
            "data-sample-origin-readonly-map",
        )

    def test_dashboard_points_respect_sample_visibility(self):
        response = self.get_as_owner(
            "samples_dashboard"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        points = response.context[
            "sample_origin_points"
        ]

        ids = {
            point[
                "sample_id"
            ]
            for point in points
        }

        self.assertIn(
            "MAP-OWN-001",
            ids,
        )

        self.assertIn(
            "MAP-PUBLIC-002",
            ids,
        )

        self.assertNotIn(
            "MAP-HIDDEN-003",
            ids,
        )

        self.assertNotIn(
            "MAP-NOCOORD-004",
            ids,
        )

    def test_dashboard_geographic_counts(self):
        response = self.get_as_owner(
            "samples_dashboard"
        )

        stats = response.context[
            "sample_dashboard_stats"
        ]

        self.assertEqual(
            stats[
                "with_coordinates"
            ],
            2,
        )

        self.assertGreaterEqual(
            stats[
                "without_coordinates"
            ],
            1,
        )

    def test_dashboard_renders_world_map_and_filters(self):
        response = self.get_as_owner(
            "samples_dashboard"
        )

        self.assertContains(
            response,
            "Sample Geographic Origins",
        )

        self.assertContains(
            response,
            "sample-origin-dashboard-map",
        )

        self.assertContains(
            response,
            "sample-origin-dashboard-points",
        )

        for element_id in (
            "sample-origin-filter-type",
            "sample-origin-filter-status",
            "sample-origin-filter-biobank",
            "sample-origin-filter-group",
            "sample-origin-filter-location",
            "sample-origin-filter-environment",
        ):
            self.assertContains(
                response,
                element_id,
            )

    def test_internal_map_keeps_exact_marine_coordinates(self):
        response = self.get_as_owner(
            "samples_dashboard"
        )

        points = response.context[
            "sample_origin_points"
        ]

        marine = next(
            point
            for point in points
            if point[
                "sample_id"
            ] == "MAP-OWN-001"
        )

        self.assertEqual(
            marine[
                "latitude"
            ],
            -28.2241,
        )

        self.assertEqual(
            marine[
                "longitude"
            ],
            -39.8872,
        )

        self.assertEqual(
            marine[
                "country_or_ocean"
            ],
            "Atlantic Ocean",
        )
