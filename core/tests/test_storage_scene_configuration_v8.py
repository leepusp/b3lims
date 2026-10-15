from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
    StorageSceneConfiguration,
)
from core.services.storage_scene_configuration_v8 import (
    get_storage_scene_projection,
    save_storage_scene_configuration,
)


class StorageSceneConfigurationV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="scene-owner-v8"
        )
        cls.other_user = get_user_model().objects.create_user(
            username="scene-other-v8"
        )

        cls.refrigerator = StorageLocation.objects.create(
            name="Refrigerator A",
            location_type="other",
        )
        cls.shelf = StorageLocation.objects.create(
            name="Shelf 2",
            location_type="shelf",
            parent=cls.refrigerator,
        )
        cls.rack = StorageLocation.objects.create(
            name="Rack 4",
            location_type="rack",
            parent=cls.shelf,
        )
        cls.unrelated = StorageLocation.objects.create(
            name="Unrelated Freezer",
            location_type="freezer",
        )


        cls.workspace = StorageWorkspace.objects.create(
            name="Scene Test Workspace",
            scope="personal",
            owner=cls.user,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.refrigerator.pk,
                cls.shelf.pk,
                cls.rack.pk,
                cls.unrelated.pk
            ]
        ).update(workspace=cls.workspace)

    def save_scene(self, **kwargs):
        options = {
            "actor": self.user,
            "name": "My refrigerator",
            "root_id": self.refrigerator.pk,
            "root_profile": "cabinet",
        }
        options.update(kwargs)
        return save_storage_scene_configuration(**options)

    def test_scene_is_persisted(self):
        scene = self.save_scene()

        scene.refresh_from_db()

        self.assertEqual(scene.owner_id, self.user.pk)
        self.assertEqual(
            scene.root_location_id,
            self.refrigerator.pk,
        )
        self.assertEqual(scene.root_profile, "cabinet")

    def test_saved_scene_projects_nested_hierarchy(self):
        scene = self.save_scene(
            profile_overrides={
                self.shelf.pk: "shelves",
                self.rack.pk: "grid",
            }
        )

        result = get_storage_scene_projection(
            actor=self.user,
            configuration_id=scene.pk,
        )

        self.assertEqual(
            [node["name"] for node in result["nodes"]],
            ["Refrigerator A", "Shelf 2", "Rack 4"],
        )
        self.assertEqual(
            result["nodes"][0]["geometry_profile"],
            "cabinet",
        )
        self.assertEqual(
            result["nodes"][2]["geometry_profile"],
            "grid",
        )

    def test_nested_rack_can_be_root(self):
        scene = self.save_scene(
            name="Rack detail",
            root_id=self.rack.pk,
            root_profile="grid",
        )

        result = get_storage_scene_projection(
            actor=self.user,
            configuration_id=scene.pk,
        )

        self.assertEqual(len(result["nodes"]), 1)
        self.assertEqual(
            result["scene_root_id"],
            self.rack.pk,
        )

    def test_other_user_cannot_read_private_scene(self):
        scene = self.save_scene()

        with self.assertRaises(PermissionDenied):
            get_storage_scene_projection(
                actor=self.other_user,
                configuration_id=scene.pk,
            )

    def test_other_user_cannot_update_scene(self):
        scene = self.save_scene()

        with self.assertRaises(PermissionDenied):
            self.save_scene(
                actor=self.other_user,
                configuration_id=scene.pk,
            )

    def test_override_outside_scene_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.save_scene(
                profile_overrides={
                    self.unrelated.pk: "grid",
                },
            )

        self.assertEqual(
            StorageSceneConfiguration.objects.count(),
            0,
        )

    def test_inactive_ancestor_rejects_scene(self):
        self.shelf.is_active = False
        self.shelf.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.save_scene(
                root_id=self.rack.pk,
            )

    def test_scene_update_keeps_same_identifier(self):
        scene = self.save_scene()

        updated = self.save_scene(
            configuration_id=scene.pk,
            name="Updated refrigerator",
            root_profile="space",
        )

        self.assertEqual(scene.pk, updated.pk)
        self.assertEqual(
            StorageSceneConfiguration.objects.count(),
            1,
        )
        self.assertEqual(updated.root_profile, "space")

    def test_duplicate_name_is_rejected(self):
        self.save_scene()

        with self.assertRaises(ValidationError):
            self.save_scene(
                root_id=self.rack.pk,
                root_profile="grid",
            )


    def test_foreign_workspace_root_is_rejected(self):
        foreign_workspace = StorageWorkspace.objects.create(
            name="Foreign Workspace",
            scope="personal",
            owner=self.other_user,
        )

        foreign_freezer = StorageLocation.objects.create(
            name="Foreign Freezer",
            location_type="freezer",
            workspace=foreign_workspace,
        )

        with self.assertRaises(PermissionDenied):
            self.save_scene(
                name="Forged Foreign Scene",
                root_id=foreign_freezer.pk,
            )

        self.assertFalse(
            StorageSceneConfiguration.objects.filter(
                name="Forged Foreign Scene",
            ).exists()
        )

    def test_saved_scene_rechecks_changed_permissions(self):
        scene = self.save_scene()

        foreign_workspace = StorageWorkspace.objects.create(
            name="Revocation Workspace",
            scope="personal",
            owner=self.other_user,
        )

        StorageLocation.objects.filter(
            pk__in=[
                self.refrigerator.pk,
                self.shelf.pk,
                self.rack.pk,
            ]
        ).update(workspace=foreign_workspace)

        with self.assertRaises(PermissionDenied):
            get_storage_scene_projection(
                actor=self.user,
                configuration_id=scene.pk,
            )

    def test_foreign_descendant_rejects_scene(self):
        foreign_workspace = StorageWorkspace.objects.create(
            name="Foreign Descendant Workspace",
            scope="personal",
            owner=self.other_user,
        )

        StorageLocation.objects.create(
            name="Unauthorized Rack",
            location_type="rack",
            parent=self.shelf,
            workspace=foreign_workspace,
        )

        with self.assertRaises(PermissionDenied):
            self.save_scene(
                name="Scene With Foreign Child",
            )

    def test_no_physical_inventory_mutation(self):
        before = list(
            StorageLocation.objects
            .order_by("pk")
            .values_list(
                "pk", "parent_id", "name", "location_type"
            )
        )

        scene = self.save_scene()

        get_storage_scene_projection(
            actor=self.user,
            configuration_id=scene.pk,
        )

        after = list(
            StorageLocation.objects
            .order_by("pk")
            .values_list(
                "pk", "parent_id", "name", "location_type"
            )
        )

        self.assertEqual(before, after)
