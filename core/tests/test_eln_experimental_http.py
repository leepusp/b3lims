"""HTTP integration tests for ELN Experimental.

These tests exercise Django URL resolution, authentication,
authorization and real template rendering using an isolated
test database. No eLabFTW connection is required.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse


class ElnExperimentalHTTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.evaluator_group = Group.objects.create(
            name="b3_eln_evaluators"
        )

        cls.evaluator = User.objects.create_user(
            **{
                User.USERNAME_FIELD: "eln_http_evaluator",
                "password": "test-only-unused-password",
            }
        )

        cls.ordinary = User.objects.create_user(
            **{
                User.USERNAME_FIELD: "eln_http_ordinary",
                "password": "test-only-unused-password",
            }
        )

        cls.evaluator.groups.add(cls.evaluator_group)

    def setUp(self):
        self.url = reverse("eln_experimental_index")

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=False)
    def test_disabled_feature_returns_404(self):
        self.client.force_login(self.evaluator)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_anonymous_request_redirects_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_ordinary_user_receives_403(self):
        self.client.force_login(self.ordinary)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_evaluator_receives_rendered_page(self):
        self.client.force_login(self.evaluator)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "internal/lab_tools/eln_experimental/index.html",
        )

        self.assertTemplateUsed(
            response,
            "internal/common/base.html",
        )

        self.assertContains(
            response,
            "ELN Experimental",
        )

        self.assertContains(
            response,
            "Integration in progress.",
        )

        self.assertContains(
            response,
            "No experiments loaded",
        )

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_evaluator_post_is_not_allowed(self):
        self.client.force_login(self.evaluator)

        response = self.client.post(
            self.url,
            data={},
        )

        self.assertEqual(response.status_code, 405)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_superuser_receives_rendered_page(self):
        self.ordinary.is_superuser = True
        self.ordinary.save(
            update_fields=["is_superuser"]
        )

        self.client.force_login(self.ordinary)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_evaluator_page_is_not_cacheable(self):
        self.client.force_login(self.evaluator)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        cache_control = response.get(
            "Cache-Control", ""
        ).lower()

        self.assertIn("no-store", cache_control)
