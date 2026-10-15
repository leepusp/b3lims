from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.storage import StorageLocation
from core.services.storage_scene_projection_v8 import (
    build_storage_scene_projection,
)


class StorageSceneProjectionV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.freezer = StorageLocation.objects.create(
            name="Freezer Regina",
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Caixa 1.1",
            parent=cls.freezer,
            location_type="box",
        )

        # Refrigerator is modeled as "other" until physical
        # type choices are expanded in a later increment.
        cls.refrigerator = StorageLocation.objects.create(
            name="Refrigerator A",
            location_type="other",
        )
        cls.shelf = StorageLocation.objects.create(
            name="Shelf 2",
            parent=cls.refrigerator,
            location_type="shelf",
        )
        cls.rack = StorageLocation.objects.create(
            name="Rack 4",
            parent=cls.shelf,
            location_type="rack",
        )

    def test_freezer_can_be_scene_root(self):
        scene = build_storage_scene_projection(
            root_id=self.freezer.pk
        )

        self.assertEqual(
            [node["name"] for node in scene["nodes"]],
            ["Freezer Regina", "Caixa 1.1"],
        )
        self.assertEqual(
            scene["nodes"][0]["geometry_profile"],
            "cabinet",
        )
        self.assertEqual(
            scene["nodes"][1]["geometry_profile"],
            "grid",
        )

    def test_refrigerator_with_nested_shelf_and_rack(self):
        scene = build_storage_scene_projection(
            root_id=self.refrigerator.pk,
            profile_overrides={
                self.refrigerator.pk: "cabinet",
            },
        )

        self.assertEqual(
            [node["name"] for node in scene["nodes"]],
            ["Refrigerator A", "Shelf 2", "Rack 4"],
        )
        self.assertEqual(
            [node["depth"] for node in scene["nodes"]],
            [0, 1, 2],
        )
        self.assertEqual(
            scene["nodes"][0]["geometry_profile"],
            "cabinet",
        )
        self.assertEqual(
            scene["nodes"][1]["geometry_profile"],
            "shelves",
        )
        self.assertEqual(
            scene["nodes"][2]["geometry_profile"],
            "rack",
        )

    def test_rack_can_be_selected_as_independent_root(self):
        scene = build_storage_scene_projection(
            root_id=self.rack.pk
        )

        self.assertEqual(len(scene["nodes"]), 1)
        self.assertEqual(
            scene["nodes"][0]["depth"],
            0,
        )
        self.assertEqual(
            scene["scene_root_path"],
            "Refrigerator A > Shelf 2 > Rack 4",
        )

    def test_inactive_child_is_not_shown_by_default(self):
        self.shelf.is_active = False
        self.shelf.save(update_fields=["is_active"])

        scene = build_storage_scene_projection(
            root_id=self.refrigerator.pk
        )

        self.assertEqual(
            [node["name"] for node in scene["nodes"]],
            ["Refrigerator A"],
        )

    def test_inactive_ancestor_blocks_root(self):
        self.shelf.is_active = False
        self.shelf.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            build_storage_scene_projection(
                root_id=self.rack.pk
            )

    def test_invalid_geometry_profile_is_rejected(self):
        with self.assertRaises(ValidationError):
            build_storage_scene_projection(
                root_id=self.freezer.pk,
                profile_overrides={
                    self.freezer.pk: "unknown_geometry",
                },
            )

    def test_scene_size_limit_is_enforced(self):
        with self.assertRaises(ValidationError):
            build_storage_scene_projection(
                root_id=self.freezer.pk,
                max_nodes=1,
            )

    def test_projection_does_not_change_inventory(self):
        before = StorageLocation.objects.count()

        scene = build_storage_scene_projection(
            root_id=self.refrigerator.pk
        )

        self.assertEqual(
            StorageLocation.objects.count(),
            before,
        )
        self.assertTrue(scene["read_only"])
        self.assertFalse(scene["sample_data_included"])

    def test_unknown_root_is_rejected(self):
        with self.assertRaises(ValidationError):
            build_storage_scene_projection(
                root_id=999999999
            )
