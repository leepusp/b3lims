from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    StorageLocation,
    StorageMovement,
    StorageMovementItem,
)


class StorageMovementAuditTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="storage-audit-test"
        )

        cls.room_a = StorageLocation.objects.create(
            name="Sala A",
            location_type="room",
        )

        cls.room_b = StorageLocation.objects.create(
            name="Sala B",
            location_type="room",
        )

        cls.box = StorageLocation.objects.create(
            name="Caixa Y",
            parent=cls.room_a,
            location_type="box",
        )

        cls.sample = Sample.objects.create(
            sample_id="AUDIT-001",
            sample_type="Other",
            organism_name="Audit Test Sample",
            owner=cls.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

    def test_container_movement_audit_persists(self):
        movement = StorageMovement.objects.create(
            movement_type="container",
            moved_location=self.box,
            origin_location=self.room_a,
            destination_location=self.room_b,
            origin_path="Sala A > Caixa Y",
            destination_path="Sala B > Caixa Y",
            affected_location_count=1,
            affected_sample_count=1,
            affected_assignment_count=1,
            performed_by=self.user,
            actor_label=self.user.username,
            reason="Transferência experimental",
        )

        StorageMovementItem.objects.create(
            movement=movement,
            sample=self.sample,
            sample_identifier=self.sample.sample_id,
            location_id_snapshot=self.box.pk,
            position_before="P03",
            position_after="P03",
            path_before="Sala A > Caixa Y",
            path_after="Sala B > Caixa Y",
        )

        movement.refresh_from_db()

        self.assertEqual(
            movement.movement_type,
            "container",
        )

        self.assertEqual(
            movement.affected_sample_count,
            1,
        )

        self.assertEqual(
            movement.items.count(),
            1,
        )

        item = movement.items.get()

        self.assertEqual(
            item.position_before,
            item.position_after,
        )

        self.assertEqual(
            item.sample_identifier,
            "AUDIT-001",
        )

    def test_snapshot_survives_sample_deletion(self):
        movement = StorageMovement.objects.create(
            movement_type="container",
            performed_by=self.user,
            actor_label=self.user.username,
        )

        item = StorageMovementItem.objects.create(
            movement=movement,
            sample=self.sample,
            sample_identifier=self.sample.sample_id,
            path_before="Sala A > Caixa Y",
            path_after="Sala B > Caixa Y",
        )

        self.sample.delete()
        item.refresh_from_db()

        self.assertIsNone(item.sample_id)
        self.assertEqual(
            item.sample_identifier,
            "AUDIT-001",
        )
        self.assertEqual(
            item.path_before,
            "Sala A > Caixa Y",
        )
