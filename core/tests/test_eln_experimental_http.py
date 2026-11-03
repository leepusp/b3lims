"""HTTP tests for the retired ELN Experimental preview."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(FORCE_SCRIPT_NAME=None, B3_ELN_EXPERIMENTAL_ENABLED=True)
class RetiredElnExperimentalHTTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="eln_retired_user",
            password="test-only-unused-password",
        )

    def setUp(self):
        self.url = reverse("eln_experimental_index")

    def test_anonymous_request_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], reverse("notebook_index"))

    def test_user_is_sent_to_the_canonical_notebook(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            reverse("notebook_index"),
            fetch_redirect_response=False,
        )

    def test_post_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_demo_records_are_gone(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, follow=True)
        self.assertNotContains(response, "DEMO-")
