from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
    StorageSceneConfiguration,
)


class StorageSceneUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="scene-ui-v8",
            is_staff=True,
        )
        cls.other = get_user_model().objects.create_user(
            username="scene-ui-other-v8",
            is_staff=True,
        )
        cls.freezer = StorageLocation.objects.create(
            name="Test Freezer",
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Test Box",
            location_type="box",
            parent=cls.freezer,
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


    def test_other_user_cannot_list_foreign_inventory(self):
        self.client.force_login(self.other)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Test Freezer")
        self.assertNotContains(response, "Test Box")

    def test_foreign_scene_root_post_is_rejected(self):
        self.client.force_login(self.other)

        response = self.client.post(
            self.url,
            {
                "action": "save_scene_configuration_v8",
                "save_operation": "create",
                "name": "Unauthorized Scene",
                "root_location_id": self.freezer.pk,
                "root_profile": "cabinet",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            StorageSceneConfiguration.objects.filter(
                name="Unauthorized Scene",
            ).exists()
        )

    def test_scene_controls_render(self):
        response = self.client.get(self.url, {"legacy": "1"})

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Configure spatial view",
        )
        self.assertContains(
            response,
            "Test Freezer",
        )

    def test_save_scene_from_workspace(self):
        response = self.client.post(
            self.url,
            {
                "action": "save_scene_configuration_v8",
                "save_operation": "create",
                "name": "My Freezer",
                "root_location_id": self.freezer.pk,
                "root_profile": "cabinet",
            },
        )

        self.assertEqual(response.status_code, 302)

        scene = StorageSceneConfiguration.objects.get(
            owner=self.user,
            name="My Freezer",
        )

        self.assertEqual(
            scene.root_location_id,
            self.freezer.pk,
        )

        self.assertIn(
            f"scene={scene.pk}",
            response["Location"],
        )

    def test_selected_scene_shows_projection(self):
        scene = StorageSceneConfiguration.objects.create(
            owner=self.user,
            name="My Freezer",
            root_location=self.freezer,
            root_profile="cabinet",
        )

        response = self.client.get(
            self.url,
            {"scene": scene.pk},
        )

        self.assertEqual(response.status_code, 200)

        projection = response.context[
            "storage_scene_projection_v8"
        ]

        self.assertEqual(
            [node["name"] for node in projection["nodes"]],
            ["Test Freezer", "Test Box"],
        )

    def test_private_scene_not_shown_to_another_user(self):
        scene = StorageSceneConfiguration.objects.create(
            owner=self.user,
            name="Private Freezer",
            root_location=self.freezer,
        )

        self.client.force_login(self.other)

        response = self.client.get(
            self.url,
            {"scene": scene.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            response.context["storage_scene_selected_v8"]
        )
        self.assertNotContains(
            response,
            "Private Freezer",
        )

    def test_update_scene_from_workspace(self):
        scene = StorageSceneConfiguration.objects.create(
            owner=self.user,
            name="Original View",
            root_location=self.freezer,
        )

        response = self.client.post(
            self.url,
            {
                "action": "save_scene_configuration_v8",
                "save_operation": "update",
                "scene_configuration_id": scene.pk,
                "name": "Updated View",
                "root_location_id": self.box.pk,
                "root_profile": "grid",
            },
        )

        self.assertEqual(response.status_code, 302)

        scene.refresh_from_db()

        self.assertEqual(scene.name, "Updated View")
        self.assertEqual(
            scene.root_location_id,
            self.box.pk,
        )
        self.assertEqual(
            scene.root_profile,
            "grid",
        )

    def test_scene_save_does_not_change_locations(self):
        before = list(
            StorageLocation.objects
            .order_by("pk")
            .values_list(
                "pk",
                "parent_id",
                "name",
                "location_type",
            )
        )

        self.client.post(
            self.url,
            {
                "action": "save_scene_configuration_v8",
                "save_operation": "create",
                "name": "Inventory Safe",
                "root_location_id": self.freezer.pk,
                "root_profile": "cabinet",
            },
        )

        after = list(
            StorageLocation.objects
            .order_by("pk")
            .values_list(
                "pk",
                "parent_id",
                "name",
                "location_type",
            )
        )

        self.assertEqual(before, after)
