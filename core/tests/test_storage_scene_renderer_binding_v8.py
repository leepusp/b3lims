from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
    StorageSceneConfiguration,
)


class StorageSceneRendererBindingV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="scene-renderer-v8",
            is_staff=True,
        )
        cls.other = get_user_model().objects.create_user(
            username="scene-renderer-other-v8",
            is_staff=True,
        )
        cls.freezer = StorageLocation.objects.create(
            name="Renderer Freezer",
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Renderer Box",
            location_type="box",
            parent=cls.freezer,
        )
        cls.saved = StorageSceneConfiguration.objects.create(
            owner=cls.user,
            name="My Renderer Scene",
            root_location=cls.freezer,
            root_profile="cabinet",
        )


        cls.workspace = StorageWorkspace.objects.create(
            name="Scene Test Workspace",
            scope="personal",
            owner=cls.user,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.freezer.pk,
                cls.box.pk
            ]
        ).update(workspace=cls.workspace)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("storage_workspace")

    def test_selected_scene_embeds_projection(self):
        response = self.client.get(self.url, {"legacy": "1", "scene": self.saved.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="storage-scene-projection-v8"',
        )
        self.assertContains(
            response,
            "storage_scene_filter_v8.js",
        )

        projection = response.context[
            "storage_scene_projection_v8"
        ]

        self.assertEqual(
            projection["scene_root_id"],
            self.freezer.pk,
        )
        self.assertEqual(
            [node["id"] for node in projection["nodes"]],
            [self.freezer.pk, self.box.pk],
        )

    def test_default_view_has_no_scene_scope(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            'id="storage-scene-projection-v8"',
        )

    def test_other_user_scene_is_not_embedded(self):
        self.client.force_login(self.other)

        response = self.client.get(
            self.url,
            {"scene": self.saved.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            'id="storage-scene-projection-v8"',
        )
