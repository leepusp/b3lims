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

    def test_sample_inventory_exposes_origin_map(self):
        response = self.client.get(
            self.client_path(
                reverse("samples_list")
            )
        )

        self.assertEqual(response.status_code, 200)

        expected_url = reverse(
            "samples_origin_map"
        )

        self.assertContains(
            response,
            "Origin Map",
        )

        self.assertContains(
            response,
            "data-sample-origin-map-link",
        )

        self.assertContains(
            response,
            f'href="{expected_url}"',
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
