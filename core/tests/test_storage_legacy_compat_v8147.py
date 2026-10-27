from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


ROOT = Path(__file__).resolve().parents[2]


class StorageLegacyRouteTests(TestCase):
    def test_modern_and_legacy_interfaces_are_separate(self):
        user = get_user_model().objects.create_user(
            username="c4g_compat_staff",
            password="c4g-test-password",
            is_staff=True,
        )

        self.client.force_login(user)
        url = reverse("storage_workspace")

        modern = self.client.get(url)
        legacy = self.client.get(
            url,
            {"legacy": "1"},
        )

        self.assertEqual(modern.status_code, 200)
        self.assertEqual(legacy.status_code, 200)

        self.assertContains(
            modern, 'id="b3-storage-v814"'
        )
        self.assertNotContains(
            modern, 'id="storage-location-explorer"'
        )

        self.assertContains(
            legacy, 'id="storage-location-explorer"'
        )
        self.assertContains(
            legacy, 'id="storage-relationship-v89"'
        )
        self.assertContains(
            legacy, 'id="storage-isometric-v813"'
        )
        self.assertNotContains(
            legacy, 'id="b3-storage-v814"'
        )


class StorageLegacySceneLinkTests(SimpleTestCase):
    def test_scene_links_preserve_legacy_mode(self):
        path = (
            ROOT
            / "core/interfaces/internal/storage"
            / "_scene_controls_v8.html"
        )

        html = path.read_text()

        self.assertIn(
            'href="?legacy=1&amp;scene={{ scene.pk }}'
            '#storage-scene-controls-v8"',
            html,
        )

        self.assertNotIn(
            'href="?scene={{ scene.pk }}'
            '#storage-scene-controls-v8"',
            html,
        )
