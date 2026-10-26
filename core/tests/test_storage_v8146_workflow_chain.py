"""V8.14.6B4: integrated physical storage workflow regressions."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageWorkspace,
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


class StorageWorkflowChainV8146Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="v8146b4-owner",
            is_staff=True,
        )

        cls.outsider = User.objects.create_user(
            username="v8146b4-outsider",
            is_staff=True,
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="V8146B4 personal workspace",
            scope="personal",
            owner=cls.owner,
        )

        cls.parent = StorageLocation.objects.create(
            name="V8146B4 Room",
            location_type="room",
            workspace=cls.workspace,
        )

        cls.source = StorageLocation.objects.create(
            name="Existing custom source",
            location_type="other",
            parent=cls.parent,
            workspace=cls.workspace,
        )

        cls.secondary_location = StorageLocation.objects.create(
            name="Secondary box",
            location_type="box",
            parent=cls.parent,
            workspace=cls.workspace,
        )

    def setUp(self):
        self.client.force_login(self.owner)

        self.child_url = reverse(
            "storage_location_child_create_v8146"
        )

    def sample(self, identifier):
        return Sample.objects.create(
            sample_id=identifier,
            sample_type="Other",
            organism_name="V8.14.6 workflow test",
            owner=self.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location="",
        )

    def create_child(self, name="BBAMS"):
        response = self.client.post(
            self.child_url,
            {
                "parent_id": str(self.parent.pk),
                "name": name,
                "location_type": "other",
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.content.decode(),
        )

        return StorageLocation.objects.get(
            pk=response.json()["anchor"]["id"]
        )

    def register(self, sample, location, position):
        return register_initial_physical_storage(
            sample=sample,
            box=location,
            position=position,
            actor=self.owner,
            mode="new",
            expected_legacy_path="",
        )

    def test_new_child_catalog_and_two_sample_registrations(self):
        child = self.create_child()

        self.assertEqual(child.name, "BBAMS")
        self.assertEqual(child.parent_id, self.parent.pk)
        self.assertEqual(
            child.workspace_id,
            self.workspace.pk,
        )

        catalog = build_storage_anchor_catalog(
            user=self.owner
        )

        matches = [
            item for item in catalog
            if item["id"] == child.pk
        ]

        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["parent_id"],
            self.parent.pk,
        )

        plan = validate_storage_anchor_plan(
            mode="physical",
            box_id=child.pk,
            positions=["A1", "A2"],
            expected_samples=2,
            actor=self.owner,
        )

        self.assertEqual(plan.box_id, child.pk)
        self.assertEqual(
            plan.positions,
            ("A1", "A2"),
        )

        first = self.sample("V8146B4-NEW-001")
        second = self.sample("V8146B4-NEW-002")

        first_assignment, first_audit = self.register(
            first, child, "A1"
        )

        second_assignment, second_audit = self.register(
            second, child, "A2"
        )

        self.assertEqual(
            first_assignment.location_id,
            second_assignment.location_id,
        )

        self.assertEqual(
            first_assignment.location_id,
            child.pk,
        )

        self.assertNotEqual(
            first_assignment.position,
            second_assignment.position,
        )

        self.assertEqual(
            first_audit.movement_type,
            "registration",
        )
        self.assertEqual(
            second_audit.movement_type,
            "registration",
        )

        self.assertEqual(
            SampleStorageAssignment.objects.filter(
                location=child,
                status="active",
            ).count(),
            2,
        )

    def test_create_child_then_audited_edit_movement(self):
        child = self.create_child(
            "User-created destination"
        )

        sample = self.sample("V8146B4-EDIT-001")

        primary, _ = self.register(
            sample, self.source, "B1"
        )

        secondary = SampleStorageAssignment.objects.create(
            sample=sample,
            location=self.secondary_location,
            rank=2,
            is_primary=False,
            position="S01",
            status="active",
        )

        move_url = reverse(
            "sample_storage_move_v8146",
            args=[sample.pk],
        )

        response = self.client.post(
            move_url,
            {
                "storage_move_assignment_v8146":
                    str(primary.pk),
                "storage_move_destination_v8146":
                    str(child.pk),
                "storage_move_position_v8146":
                    "C7",
                "storage_move_reason_v8146":
                    "Relocation to a user-created location.",
                "storage_move_expected_location_v8146":
                    str(self.source.pk),
                "storage_move_expected_position_v8146":
                    "B1",
                "storage_move_expected_source_path_v8146":
                    self.source.full_path,
                "storage_move_expected_destination_path_v8146":
                    child.full_path,
            },
        )

        self.assertEqual(response.status_code, 302)

        primary.refresh_from_db()
        secondary.refresh_from_db()
        sample.refresh_from_db()

        self.assertEqual(primary.location_id, child.pk)
        self.assertEqual(primary.position, "C7")

        self.assertEqual(
            secondary.location_id,
            self.secondary_location.pk,
        )
        self.assertEqual(
            secondary.position,
            "S01",
        )

        self.assertIn(
            child.full_path,
            sample.storage_location,
        )

        movement = StorageMovement.objects.get(
            movement_type="sample"
        )

        self.assertEqual(
            movement.destination_location_id,
            child.pk,
        )

        self.assertEqual(
            movement.items.count(),
            1,
        )

    def test_new_child_does_not_disable_slot_collision(self):
        child = self.create_child(
            "Shared location with distinct slots"
        )

        first = self.sample("V8146B4-SLOT-001")
        second = self.sample("V8146B4-SLOT-002")

        self.register(first, child, "D4")

        with self.assertRaises(ValidationError):
            self.register(second, child, "D4")

        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=second,
            ).exists()
        )

        self.assertEqual(
            SampleStorageAssignment.objects.filter(
                location=child,
                position="D4",
                status="active",
            ).count(),
            1,
        )

    def test_foreign_user_cannot_create_child(self):
        self.client.force_login(self.outsider)

        before = StorageLocation.objects.count()

        response = self.client.post(
            self.child_url,
            {
                "parent_id": str(self.parent.pk),
                "name": "Unauthorized child",
                "location_type": "other",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            StorageLocation.objects.count(),
            before,
        )
