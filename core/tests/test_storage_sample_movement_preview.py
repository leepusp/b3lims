from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
)
from core.services.storage_sample_movement_preview import (
    preview_sample_movements,
)


class StorageSampleMovementPreviewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="d3-owner")
        cls.other = User.objects.create_user(username="d3-other")

        cls.room = StorageLocation.objects.create(
            name="D3 Room", location_type="room"
        )
        cls.box_a = StorageLocation.objects.create(
            name="D3 Box A", location_type="box", parent=cls.room
        )
        cls.box_b = StorageLocation.objects.create(
            name="D3 Box B", location_type="box", parent=cls.room
        )
        cls.shelf = StorageLocation.objects.create(
            name="D3 Shelf", location_type="shelf", parent=cls.room
        )

        cls.assignments = []

        for i, (owner, location, position) in enumerate((
            (cls.owner, cls.box_a, "P01"),
            (cls.owner, cls.box_b, "P02"),
            (cls.owner, cls.box_a, "P03"),
            (cls.other, cls.box_b, "P09"),
        ), 1):
            sample = Sample.objects.create(
                sample_id=f"D3-{i}",
                sample_type="Other",
                organism_name=f"D3 sample {i}",
                owner=owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )
            cls.assignments.append(
                SampleStorageAssignment.objects.create(
                    sample=sample,
                    location=location,
                    rank=1,
                    is_primary=True,
                    position=position,
                    status="active",
                )
            )

        cls.secondary = SampleStorageAssignment.objects.create(
            sample=cls.assignments[0].sample,
            location=cls.shelf,
            rank=2,
            is_primary=False,
            position="S01",
            status="active",
        )

    def move(self, assignment, destination, position):
        return {
            "assignment_id": assignment.pk,
            "destination_id": destination.pk,
            "position": position,
        }

    def test_individual_preview_preserves_database(self):
        assignment = self.assignments[0]
        before = (assignment.location_id, assignment.position)

        result = preview_sample_movements(
            moves=[self.move(assignment, self.box_b, "P04")],
            actor=self.owner,
        )

        self.assertTrue(result["preview_only"])
        self.assertEqual(result["affected_assignment_count"], 1)
        self.assertEqual(result["affected_sample_count"], 1)
        self.assertEqual(result["moves"][0]["position_before"], "P01")
        self.assertEqual(result["moves"][0]["position_after"], "P04")

        assignment.refresh_from_db()
        self.secondary.refresh_from_db()

        self.assertEqual(
            (assignment.location_id, assignment.position),
            before,
        )
        self.assertEqual(self.secondary.position, "S01")
        self.assertFalse(StorageMovement.objects.exists())

    def test_occupied_position_rejected_case_insensitively(self):
        with self.assertRaises(ValidationError):
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[0], self.box_b, "p02")
                ],
                actor=self.owner,
            )

    def test_hidden_occupant_identity_not_disclosed(self):
        with self.assertRaises(ValidationError) as caught:
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[0], self.box_b, "P09")
                ],
                actor=self.owner,
            )

        self.assertNotIn("D3-4", str(caught.exception))

    def test_permission_denied_for_other_sample(self):
        with self.assertRaises(PermissionDenied):
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[3], self.box_a, "P08")
                ],
                actor=self.owner,
            )

    def test_mixed_bulk_is_denied(self):
        with self.assertRaises(PermissionDenied):
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[0], self.box_b, "P04"),
                    self.move(self.assignments[3], self.box_a, "P08"),
                ],
                actor=self.owner,
            )

    def test_position_swap_is_previewable(self):
        result = preview_sample_movements(
            moves=[
                self.move(self.assignments[0], self.box_a, "P03"),
                self.move(self.assignments[2], self.box_a, "P01"),
            ],
            actor=self.owner,
        )

        self.assertEqual(result["affected_assignment_count"], 2)
        self.assertEqual(result["affected_sample_count"], 2)
        self.assertFalse(StorageMovement.objects.exists())

    def test_batch_collision_is_rejected(self):
        with self.assertRaises(ValidationError):
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[0], self.box_b, "P04"),
                    self.move(self.assignments[2], self.box_b, "P04"),
                ],
                actor=self.owner,
            )

    def test_existing_secondary_is_not_duplicated(self):
        with self.assertRaises(ValidationError):
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[0], self.shelf, "S02")
                ],
                actor=self.owner,
            )

    def test_inactive_ancestor_is_rejected(self):
        self.room.is_active = False
        self.room.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            preview_sample_movements(
                moves=[
                    self.move(self.assignments[0], self.box_b, "P04")
                ],
                actor=self.owner,
            )

    def test_duplicate_assignment_is_rejected(self):
        entry = self.move(self.assignments[0], self.box_b, "P04")

        with self.assertRaises(ValidationError):
            preview_sample_movements(
                moves=[entry, entry],
                actor=self.owner,
            )
