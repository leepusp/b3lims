from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageMovementItem,
)
from core.services.storage_sample_movements import (
    move_sample,
    move_samples_bulk,
)


class StorageSampleMovementTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="c3-owner"
        )
        cls.viewer = User.objects.create_user(
            username="c3-viewer"
        )

        cls.room = StorageLocation.objects.create(
            name="Sala C3",
            location_type="room",
        )

        cls.box_a = StorageLocation.objects.create(
            name="Caixa A",
            parent=cls.room,
            location_type="box",
        )
        cls.box_b = StorageLocation.objects.create(
            name="Caixa B",
            parent=cls.room,
            location_type="box",
        )
        cls.shelf = StorageLocation.objects.create(
            name="Prateleira",
            parent=cls.room,
            location_type="shelf",
        )

        cls.samples = []

        for index in range(1, 4):
            sample = Sample.objects.create(
                sample_id=f"C3-{index:03d}",
                sample_type="Other",
                organism_name=f"C3 Sample {index}",
                owner=cls.owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )
            cls.samples.append(sample)

        cls.a = SampleStorageAssignment.objects.create(
            sample=cls.samples[0],
            location=cls.box_a,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )

        cls.secondary = (
            SampleStorageAssignment.objects.create(
                sample=cls.samples[0],
                location=cls.shelf,
                rank=2,
                is_primary=False,
                position="S01",
                status="active",
            )
        )

        cls.b = SampleStorageAssignment.objects.create(
            sample=cls.samples[1],
            location=cls.box_b,
            rank=1,
            is_primary=True,
            position="P02",
            status="active",
        )

        cls.c = SampleStorageAssignment.objects.create(
            sample=cls.samples[2],
            location=cls.box_a,
            rank=1,
            is_primary=True,
            position="P03",
            status="active",
        )

    def request(self, assignment, destination, position):
        return {
            "assignment_id": assignment.pk,
            "destination_id": destination.pk,
            "position": position,
            "expected_location_id": assignment.location_id,
            "expected_position": assignment.position,
            "expected_source_path": (
                assignment.location.full_path
            ),
            "expected_destination_path": (
                destination.full_path
            ),
        }

    def test_individual_move_preserves_secondary(self):
        original_secondary_id = self.secondary.pk

        movement = move_sample(
            **self.request(self.a, self.box_b, "P04"),
            actor=self.owner,
            reason="Individual movement test",
        )

        self.a.refresh_from_db()
        self.secondary.refresh_from_db()
        self.samples[0].refresh_from_db()

        self.assertEqual(self.a.location_id, self.box_b.pk)
        self.assertEqual(self.a.position, "P04")
        self.assertEqual(
            self.secondary.pk, original_secondary_id
        )
        self.assertEqual(self.secondary.position, "S01")
        self.assertEqual(
            self.samples[0].storage_location,
            self.box_b.full_path,
        )
        self.assertEqual(movement.movement_type, "sample")
        self.assertEqual(movement.items.count(), 1)

    def test_occupied_position_is_rejected(self):
        with self.assertRaises(ValidationError):
            move_sample(
                **self.request(self.a, self.box_b, "P02"),
                actor=self.owner,
                reason="Occupied position test",
            )

        self.a.refresh_from_db()
        self.assertEqual(self.a.location_id, self.box_a.pk)
        self.assertFalse(StorageMovement.objects.exists())

    def test_bulk_moves_two_selected_assignments(self):
        movement = move_samples_bulk(
            moves=[
                self.request(self.a, self.box_b, "P04"),
                self.request(self.c, self.box_b, "P05"),
            ],
            actor=self.owner,
            reason="Bulk movement test",
        )

        self.a.refresh_from_db()
        self.c.refresh_from_db()
        self.b.refresh_from_db()

        self.assertEqual(self.a.position, "P04")
        self.assertEqual(self.c.position, "P05")
        self.assertEqual(self.b.position, "P02")
        self.assertEqual(movement.movement_type, "sample_bulk")
        self.assertEqual(movement.affected_sample_count, 2)
        self.assertEqual(movement.items.count(), 2)

    def test_bulk_collision_rolls_back(self):
        with self.assertRaises(ValidationError):
            move_samples_bulk(
                moves=[
                    self.request(self.a, self.box_b, "P04"),
                    self.request(self.c, self.box_b, "P04"),
                ],
                actor=self.owner,
                reason="Collision test",
            )

        self.a.refresh_from_db()
        self.c.refresh_from_db()

        self.assertEqual(self.a.location_id, self.box_a.pk)
        self.assertEqual(self.c.location_id, self.box_a.pk)
        self.assertFalse(StorageMovement.objects.exists())

    def test_non_owner_cannot_move(self):
        with self.assertRaises(PermissionDenied):
            move_sample(
                **self.request(self.a, self.box_b, "P04"),
                actor=self.viewer,
                reason="Unauthorized test",
            )

        self.a.refresh_from_db()
        self.assertEqual(self.a.location_id, self.box_a.pk)

    def test_stale_source_path_is_rejected(self):
        request = self.request(self.a, self.box_b, "P04")
        request["expected_source_path"] = "Local antigo"

        with self.assertRaises(ValidationError):
            move_sample(
                **request,
                actor=self.owner,
                reason="Stale movement test",
            )

        self.assertFalse(StorageMovement.objects.exists())

    def test_swapping_positions_in_one_batch(self):
        movement = move_samples_bulk(
            moves=[
                self.request(self.a, self.box_a, "P03"),
                self.request(self.c, self.box_a, "P01"),
            ],
            actor=self.owner,
            reason="Swap positions",
        )

        self.a.refresh_from_db()
        self.c.refresh_from_db()

        self.assertEqual(self.a.position, "P03")
        self.assertEqual(self.c.position, "P01")
        self.assertEqual(movement.items.count(), 2)

    def test_audit_failure_rolls_back_all_moves(self):
        with patch.object(
            StorageMovementItem.objects,
            "bulk_create",
            side_effect=RuntimeError("Audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                move_samples_bulk(
                    moves=[
                        self.request(
                            self.a, self.box_b, "P04"
                        ),
                        self.request(
                            self.c, self.box_b, "P05"
                        ),
                    ],
                    actor=self.owner,
                    reason="Rollback validation",
                )

        self.a.refresh_from_db()
        self.c.refresh_from_db()

        self.assertEqual(self.a.location_id, self.box_a.pk)
        self.assertEqual(self.c.location_id, self.box_a.pk)
        self.assertFalse(StorageMovement.objects.exists())
        self.assertFalse(StorageMovementItem.objects.exists())
