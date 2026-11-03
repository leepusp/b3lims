from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bench.tests.test_home import request_path


class BenchSidebarTests(TestCase):
    def test_sidebar_shows_bench_group(self):
        user = get_user_model().objects.create_user(username="bench-sidebar-user", password="x")
        self.client.force_login(user)

        response = self.client.get(request_path("bench:home"))

        self.assertContains(response, 'nav-section-label">Laboratory<')
        self.assertContains(response, reverse("bench:home"))
