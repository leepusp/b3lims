"""V8.14.6A: custom physical locations and shared containers."""

from django.contrib.auth import get_user_model
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.permissions.storage_workspaces_v8 import (
    can_register_at_storage_location,
)
from core.services.storage_anchor_catalog_v8 import (
    build_storage_anchor_catalog,
)
from core.services.storage_anchor_v8 import (
    validate_storage_anchor_plan,
)
from core.services.storage_registration_v8 import (
    register_initial_physical_storage,
)
from core.services.storage_sample_movements import (
    move_sample,
)


class CustomStorageLocationV8146ATests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="v8146a-owner",
        )

        cls.outsider = User.objects.create_user(
            username="v8146a-outsider",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="V8146A custom storage",
            scope="personal",
            owner=cls.owner,
        )

        cls.room = StorageLocation.objects.create(
            name="My Room",
            location_type="room",
            workspace=cls.workspace,
        )

        cls.freezer = StorageLocation.objects.create(
            name="A custom named freezer",
            location_type="freezer",
            workspace=cls.workspace,
            parent=cls.room,
        )

        cls.destination_a = StorageLocation.objects.create(
            name="BBAMS",
            location_type="other",
            workspace=cls.workspace,
            parent=cls.freezer,
        )

        cls.destination_b = StorageLocation.objects.create(
            name="User defined location",
            location_type="other",
            workspace=cls.workspace,
            parent=cls.freezer,
        )

    def sample(self, identifier):
        return Sample.objects.create(
            sample_id=identifier,
            sample_type="Other",
            organism_name="V8146A test material",
            owner=self.owner,
            status="available",
            aliquot_count=1,
            is_active=True,
            storage_location="",
        )

    def register(self, sample, position):
        return register_initial_physical_storage(
            sample=sample,
            box=self.destination_a,
            position=position,
            actor=self.owner,
            mode="new",
            expected_legacy_path="",
        )

    def test_catalog_preserves_names_and_parent_ids(self):
        catalog = build_storage_anchor_catalog(
            user=self.owner
        )

        node = next(
            row for row in catalog
            if row["id"] == self.destination_a.pk
        )

        self.assertEqual(node["name"], "BBAMS")
        self.assertEqual(
            node["parent_id"],
            self.freezer.pk,
        )
        self.assertEqual(
            node["location_type"],
            "other",
        )
        self.assertEqual(
            node["full_path"],
            self.destination_a.full_path,
        )

    def test_custom_location_is_authorized(self):
        self.assertTrue(
            can_register_at_storage_location(
                self.owner,
                self.destination_a,
            )
        )

        self.assertFalse(
            can_register_at_storage_location(
                self.outsider,
                self.destination_a,
            )
        )

        with self.assertRaises(PermissionDenied):
            validate_storage_anchor_plan(
                mode="physical",
                box_id=self.destination_a.pk,
                positions=["A1"],
                expected_samples=1,
                actor=self.outsider,
            )

    def test_plan_accepts_user_named_destination(self):
        plan = validate_storage_anchor_plan(
            mode="physical",
            box_id=self.destination_a.pk,
            positions=["A1", "B5"],
            expected_samples=2,
            actor=self.owner,
        )

        self.assertEqual(
            plan.box_id,
            self.destination_a.pk,
        )
        self.assertEqual(
            plan.positions,
            ("A1", "B5"),
        )

    def test_two_samples_share_same_location(self):
        first = self.sample("V8146A-SHARE-001")
        second = self.sample("V8146A-SHARE-002")

        first_assignment, first_audit = (
            self.register(first, "A1")
        )

        second_assignment, second_audit = (
            self.register(second, "B5")
        )

        self.assertEqual(
            first_assignment.location_id,
            second_assignment.location_id,
        )
        self.assertEqual(
            first_assignment.location_id,
            self.destination_a.pk,
        )

        self.assertEqual(
            SampleStorageAssignment.objects.filter(
                location=self.destination_a,
                status="active",
            ).count(),
            2,
        )

        self.assertEqual(
            first_audit.movement_type,
            "registration",
        )

        self.assertEqual(
            second_audit.movement_type,
            "registration",
        )

    def test_occupied_position_is_rejected(self):
        first = self.sample("V8146A-OCCUPIED-001")
        second = self.sample("V8146A-OCCUPIED-002")

        self.register(first, "B5")

        with self.assertRaises(ValidationError):
            self.register(second, "B5")

        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=second
            ).exists()
        )

    def test_move_preserves_other_sample(self):
        first = self.sample("V8146A-MOVE-001")
        second = self.sample("V8146A-MOVE-002")

        moving, _ = self.register(first, "A1")
        remaining, _ = self.register(second, "B5")

        movement = move_sample(
            assignment_id=moving.pk,
            destination_id=self.destination_b.pk,
            position="C7",
            expected_location_id=self.destination_a.pk,
            expected_position="A1",
            expected_source_path=self.destination_a.full_path,
            expected_destination_path=self.destination_b.full_path,
            actor=self.owner,
            reason="Test relocation with custom storage names.",
        )

        moving.refresh_from_db()
        remaining.refresh_from_db()

        self.assertEqual(
            moving.location_id,
            self.destination_b.pk,
        )
        self.assertEqual(moving.position, "C7")

        self.assertEqual(
            remaining.location_id,
            self.destination_a.pk,
        )
        self.assertEqual(remaining.position, "B5")

        self.assertEqual(
            movement.movement_type,
            "sample",
        )
        self.assertEqual(
            movement.items.count(),
            1,
        )

    def test_inactive_ancestor_blocks_registration(self):
        self.freezer.is_active = False
        self.freezer.save(update_fields=["is_active"])

        self.assertFalse(
            can_register_at_storage_location(
                self.owner,
                self.destination_a,
            )
        )

        with self.assertRaises(ValidationError):
            validate_storage_anchor_plan(
                mode="physical",
                box_id=self.destination_a.pk,
                positions=["A1"],
                expected_samples=1,
                actor=self.owner,
            )

    def test_any_level_can_host_samples(self):
        shelf = StorageLocation.objects.create(
            name="User-named shelf",
            location_type="shelf",
            workspace=self.workspace,
            parent=self.freezer,
        )

        for location in (self.room, self.freezer, shelf):
            with self.subTest(location_type=location.location_type):
                self.assertTrue(
                    can_register_at_storage_location(
                        self.owner,
                        location,
                    )
                )

                plan = validate_storage_anchor_plan(
                    mode="physical",
                    box_id=location.pk,
                    positions=["B2"],
                    expected_samples=1,
                    actor=self.owner,
                )
                self.assertEqual(plan.box_id, location.pk)

    def test_legacy_position_nodes_are_not_hosts(self):
        node = StorageLocation.objects.create(
            name="P1",
            location_type="position",
            workspace=self.workspace,
            parent=self.freezer,
        )

        self.assertFalse(
            can_register_at_storage_location(self.owner, node)
        )

    def test_position_node_is_not_a_destination(self):
        position_node = StorageLocation.objects.create(
            name="Position B5",
            location_type="position",
            parent=self.destination_a,
            workspace=self.workspace,
        )

        self.assertFalse(
            can_register_at_storage_location(
                self.owner,
                position_node,
            )
        )

        catalog = build_storage_anchor_catalog(
            user=self.owner
        )

        self.assertNotIn(
            position_node.pk,
            {item["id"] for item in catalog},
        )
