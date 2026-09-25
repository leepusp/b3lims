from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import (
    SimpleTestCase,
    TestCase,
)
from django.urls import reverse

from core.services.geocoding import (
    GeocodingUnavailable,
    reverse_location,
    search_locations,
)


ROOT = Path(__file__).resolve().parents[2]


class GeocodingServiceTests(
    SimpleTestCase
):
    @patch(
        "core.services.geocoding."
        "_serialized_upstream_request"
    )
    def test_search_normalizes_provider_result(
        self,
        request_mock,
    ):
        request_mock.return_value = [
            {
                "place_id": 123,
                "lat": "-23.559",
                "lon": "-46.730",
                "display_name": (
                    "Avenida Professor "
                    "Lineu Prestes, "
                    "São Paulo, Brasil"
                ),
                "type": "primary",
                "address": {
                    "road": (
                        "Avenida Professor "
                        "Lineu Prestes"
                    ),
                    "city": "São Paulo",
                    "state": "São Paulo",
                    "country": "Brasil",
                    "country_code": "br",
                },
            }
        ]

        results = search_locations(
            "Avenida Lineu Prestes"
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0]["lat"],
            "-23.5590000",
        )

        self.assertEqual(
            results[0]["lon"],
            "-46.7300000",
        )

        self.assertEqual(
            results[0]["address"]["city"],
            "São Paulo",
        )

        self.assertLessEqual(
            len(
                results[0]["label"]
            ),
            255,
        )

    @patch(
        "core.services.geocoding."
        "_serialized_upstream_request"
    )
    def test_reverse_normalizes_provider_result(
        self,
        request_mock,
    ):
        request_mock.return_value = {
            "lat": "-23.559",
            "lon": "-46.730",
            "display_name": (
                "Cidade Universitária, "
                "São Paulo, Brasil"
            ),
            "address": {
                "city": "São Paulo",
                "state": "São Paulo",
                "country": "Brasil",
            },
        }

        result = reverse_location(
            "-23.559",
            "-46.730",
        )

        self.assertEqual(
            result["address"]["state"],
            "São Paulo",
        )

    def test_invalid_coordinates_are_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            reverse_location(
                "1000",
                "0",
            )


class GeocodingViewTests(
    TestCase
):
    def setUp(self):
        self.user = (
            User.objects.create_user(
                username="geocoder",
                password="test-password",
            )
        )

    def test_search_requires_authentication(
        self,
    ):
        response = self.client.get(
            reverse(
                "biobank_geocode_search"
            ),
            {
                "q": "São Paulo",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    @patch(
        "core.views.internal.biobanks."
        "geocoding.search_locations"
    )
    def test_authenticated_search_returns_results(
        self,
        search_mock,
    ):
        self.client.force_login(
            self.user
        )

        search_mock.return_value = [
            {
                "display_name": (
                    "São Paulo, Brasil"
                ),
                "label": (
                    "São Paulo, Brasil"
                ),
                "lat": "-23.5500000",
                "lon": "-46.6300000",
                "address": {
                    "city": "São Paulo",
                    "country": "Brasil",
                },
            }
        ]

        response = self.client.get(
            reverse(
                "biobank_geocode_search"
            ),
            {
                "q": "São Paulo",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(
                response.json()[
                    "results"
                ]
            ),
            1,
        )

        search_mock.assert_called_once_with(
            "São Paulo",
            limit=5,
        )

    def test_short_search_is_rejected(
        self,
    ):
        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "biobank_geocode_search"
            ),
            {
                "q": "SP",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch(
        "core.views.internal.biobanks."
        "geocoding.reverse_location"
    )
    def test_authenticated_reverse_returns_result(
        self,
        reverse_mock,
    ):
        self.client.force_login(
            self.user
        )

        reverse_mock.return_value = {
            "display_name": (
                "São Paulo, Brasil"
            ),
            "label": (
                "São Paulo, Brasil"
            ),
            "lat": "-23.5500000",
            "lon": "-46.6300000",
            "address": {},
        }

        response = self.client.get(
            reverse(
                "biobank_geocode_reverse"
            ),
            {
                "lat": "-23.55",
                "lon": "-46.63",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()[
                "result"
            ]["label"],
            "São Paulo, Brasil",
        )

    @patch(
        "core.views.internal.biobanks."
        "geocoding.search_locations"
    )
    def test_upstream_failure_is_503(
        self,
        search_mock,
    ):
        self.client.force_login(
            self.user
        )

        search_mock.side_effect = (
            GeocodingUnavailable()
        )

        response = self.client.get(
            reverse(
                "biobank_geocode_search"
            ),
            {
                "q": "São Paulo",
            },
        )

        self.assertEqual(
            response.status_code,
            503,
        )


class GeocodingFrontendContractTests(
    SimpleTestCase
):
    def test_browser_has_no_direct_nominatim_calls(
        self,
    ):
        source = (
            ROOT
            / "core"
            / "static"
            / "internal"
            / "biobanks"
            / "biobank.js"
        ).read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "nominatim.openstreetmap.org",
            source,
        )

        self.assertIn(
            "locationSearchButton",
            source,
        )

        self.assertIn(
            'event.key !== "Enter"',
            source,
        )

    def test_template_exposes_internal_endpoints(
        self,
    ):
        source = (
            ROOT
            / "core"
            / "interfaces"
            / "internal"
            / "biobanks"
            / "biobank_create.html"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "biobank_geocode_search",
            source,
        )

        self.assertIn(
            "biobank_geocode_reverse",
            source,
        )

        self.assertIn(
            "20260925-street-basemap1",
            source,
        )

    def test_service_is_only_nominatim_runtime_owner(
        self,
    ):
        source = (
            ROOT
            / "core"
            / "services"
            / "geocoding.py"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "nominatim.openstreetmap.org",
            source,
        )

        self.assertIn(
            "MIN_REQUEST_INTERVAL_SECONDS",
            source,
        )

        self.assertIn(
            "B3LIMS_NOMINATIM_USER_AGENT",
            source,
        )
