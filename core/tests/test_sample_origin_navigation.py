from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class SampleOriginNavigationTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="originmapnav",
            password="test-password",
        )

        self.client.force_login(self.user)

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(settings, "FORCE_SCRIPT_NAME", "")
            or ""
        )

        if prefix and url.startswith(prefix):
            return url[len(prefix):] or "/"

        return url

    def test_sample_inventory_uses_dashboard_for_geographic_navigation(self):
        inventory = self.client.get(
            reverse("samples_list")
        )

        self.assertEqual(
            inventory.status_code,
            200,
        )

        self.assertContains(
            inventory,
            reverse("samples_dashboard"),
        )

        self.assertNotContains(
            inventory,
            reverse("samples_origin_map"),
        )

        self.assertNotContains(
            inventory,
            "data-sample-origin-map-link",
        )

        dashboard = self.client.get(
            reverse("samples_dashboard")
        )

        self.assertEqual(
            dashboard.status_code,
            200,
        )

        self.assertContains(
            dashboard,
            'id="sample-origin-map"',
        )

        self.assertContains(
            dashboard,
            "Sample Geographic Origins",
        )

        for hook in (
            'id="sample-origin-filter-search"',
            'id="sample-origin-filter-type"',
            'id="sample-origin-filter-status"',
            'id="sample-origin-filter-biobank"',
            'id="sample-origin-filter-group"',
            'id="sample-origin-filter-location"',
            'id="sample-origin-filter-site"',
            'id="sample-origin-filter-environment"',
            'id="sample-origin-filter-habitat"',
            'id="sample-origin-filter-broad-scale"',
            'id="sample-origin-filter-local-scale"',
            'id="sample-origin-filter-reset"',
        ):
            self.assertContains(
                dashboard,
                hook,
            )

    def test_dashboard_exposes_origin_map_anchor(self):
        response = self.client.get(
            self.client_path(
                reverse("samples_dashboard")
            )
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'id="sample-origin-map"',
        )

        self.assertContains(
            response,
            "data-sample-origin-map-section",
        )

        self.assertContains(
            response,
            "Sample Geographic Origins",
        )

        self.assertContains(
            response,
            "sample-origin-dashboard-points",
        )

        self.assertContains(
            response,
            (
                "None of the Samples visible to your account "
                "currently has"
            ),
        )

        self.assertNotContains(
            response,
            "data-sample-origin-dashboard",
        )
