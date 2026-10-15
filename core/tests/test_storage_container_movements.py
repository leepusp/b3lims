from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
    StorageMovement,
    StorageMovementItem,
)
from core.services.storage_container_movements import (
    move_storage_container,
)


class StorageContainerMovementTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.manager = User.objects.create_user(
            username="storage-manager",
            is_staff=True,
        )
        cls.viewer = User.objects.create_user(
            username="storage-viewer",
        )

        cls.room = StorageLocation.objects.create(
            name="Sala A",
            location_type="room",
        )
        cls.freezer_a = StorageLocation.objects.create(
            name="Freezer A",
            parent=cls.room,
            location_type="freezer",
        )
        cls.freezer_b = StorageLocation.objects.create(
            name="Freezer B",
            parent=cls.room,
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Caixa Y",
            parent=cls.freezer_a,
            location_type="box",
        )

        for index in range(1, 11):
            sample = Sample.objects.create(
                sample_id=f"MOVE-{index:03d}",
                sample_type="Other",
                organism_name=f"Test Sample {index}",
                owner=cls.manager,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )
            SampleStorageAssignment.objects.create(
                sample=sample,
                location=cls.box,
                rank=1,
                is_primary=True,
                position=f"P{index:02d}",
                status="active",
            )

        cls.workspace = StorageWorkspace.objects.create(
            name="Legacy Container Test Workspace",
            scope="personal",
            owner=cls.manager,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.room.pk,
                cls.freezer_a.pk,
                cls.freezer_b.pk,
                cls.box.pk,
            ]
        ).update(workspace=cls.workspace)

    def move(self, *, actor=None, expected_parent_id=None):
        return move_storage_container(
            container=self.box,
            destination=self.freezer_b,
            actor=actor or self.manager,
            expected_parent_id=(
                self.freezer_a.pk
                if expected_parent_id is None
                else expected_parent_id
            ),
            reason="Reorganização do freezer",
        )

    def test_move_preserves_positions_and_creates_audit(self):
        original = list(
            SampleStorageAssignment.objects
            .filter(location=self.box)
            .order_by("position")
            .values_list("pk", "position")
        )

        movement = self.move()

        self.box.refresh_from_db()

        self.assertEqual(
            self.box.parent_id,
            self.freezer_b.pk,
        )

        self.assertEqual(
            list(
                SampleStorageAssignment.objects
                .filter(location=self.box)
                .order_by("position")
                .values_list("pk", "position")
            ),
            original,
        )

        self.assertEqual(
            movement.affected_sample_count,
            10,
        )
        self.assertEqual(
            movement.items.count(),
            10,
        )
        self.assertTrue(
            all(
                item.position_before == item.position_after
                for item in movement.items.all()
            )
        )
        self.assertTrue(
            all(
                item.path_after
                == "Sala A > Freezer B > Caixa Y"
                for item in movement.items.all()
            )
        )

    def test_rejects_stale_parent_without_mutation(self):
        with self.assertRaises(ValidationError):
            self.move(expected_parent_id=self.room.pk)

        self.box.refresh_from_db()
        self.assertEqual(self.box.parent_id, self.freezer_a.pk)
        self.assertFalse(StorageMovement.objects.exists())

    def test_non_manager_cannot_move_container(self):
        with self.assertRaises(PermissionDenied):
            self.move(actor=self.viewer)

        self.box.refresh_from_db()
        self.assertEqual(self.box.parent_id, self.freezer_a.pk)

    def test_audit_failure_rolls_back_container_move(self):
        with patch.object(
            StorageMovementItem.objects,
            "bulk_create",
            side_effect=RuntimeError("Simulated audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.move()

        self.box.refresh_from_db()

        self.assertEqual(
            self.box.parent_id,
            self.freezer_a.pk,
        )
        self.assertFalse(StorageMovement.objects.exists())
        self.assertFalse(StorageMovementItem.objects.exists())
