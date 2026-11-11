from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


def request_path(name):
    path = reverse(name)
    script_name = settings.FORCE_SCRIPT_NAME or ""
    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"
    return path


class BenchHomeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="bench-home-user",
            password="test-password",
        )

    def test_home_requires_login(self):
        response = self.client.get(request_path("bench:home"))
        self.assertEqual(response.status_code, 302)

    def test_home_lists_modules_and_links_existing_screens(self):
        self.client.force_login(self.user)
        response = self.client.get(request_path("bench:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laboratory")
        self.assertContains(response, "ELN Notebook")
        self.assertContains(response, reverse("notebook_index"))
        self.assertContains(response, reverse("lab_calendar"))
