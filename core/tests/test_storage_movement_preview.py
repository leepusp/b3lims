from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.storage import StorageLocation
from core.services.storage_movement_preview import (
    preview_storage_container_move,
)


class StorageMovementPreviewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.room_a = StorageLocation.objects.create(
            name="Sala A",
            location_type="room",
        )
        cls.room_b = StorageLocation.objects.create(
            name="Sala B",
            location_type="room",
        )

        cls.freezer_a = StorageLocation.objects.create(
            name="Freezer A",
            parent=cls.room_a,
            location_type="freezer",
        )
        cls.freezer_b = StorageLocation.objects.create(
            name="Freezer B",
            parent=cls.room_b,
            location_type="freezer",
        )

        cls.box = StorageLocation.objects.create(
            name="Caixa Y",
            parent=cls.freezer_a,
            location_type="box",
        )

    def test_valid_preview_does_not_move_container(self):
        result = preview_storage_container_move(
            container=self.box,
            destination=self.freezer_b,
        )

        self.assertEqual(
            result["new_path"],
            "Sala B > Freezer B > Caixa Y",
        )

        self.box.refresh_from_db()

        self.assertEqual(
            self.box.parent_id,
            self.freezer_a.pk,
        )

    def test_cannot_move_parent_into_descendant(self):
        with self.assertRaises(ValidationError):
            preview_storage_container_move(
                container=self.freezer_a,
                destination=self.box,
            )

    def test_cannot_move_container_into_itself(self):
        with self.assertRaises(ValidationError):
            preview_storage_container_move(
                container=self.box,
                destination=self.box,
            )

    def test_inactive_destination_is_rejected(self):
        self.freezer_b.is_active = False
        self.freezer_b.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            preview_storage_container_move(
                container=self.box,
                destination=self.freezer_b,
            )

    def test_duplicate_name_at_destination_is_rejected(self):
        StorageLocation.objects.create(
            name="Caixa Y",
            parent=self.freezer_b,
            location_type="box",
        )

        with self.assertRaises(ValidationError):
            preview_storage_container_move(
                container=self.box,
                destination=self.freezer_b,
            )

    def test_preview_counts_ten_samples(self):
        from django.contrib.auth import get_user_model

        from core.models.samples.sample import Sample
        from core.models.samples.storage import (
            SampleStorageAssignment,
        )

        owner = get_user_model().objects.create_user(
            username="storage-impact-owner"
        )

        original_ids = []

        for index in range(1, 11):
            sample = Sample.objects.create(
                sample_id=f"IMPACT-{index:03d}",
                sample_type="Other",
                organism_name=f"Sample {index}",
                owner=owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )

            assignment = SampleStorageAssignment.objects.create(
                sample=sample,
                location=self.box,
                rank=1,
                is_primary=True,
                position=f"P{index:02d}",
                status="active",
            )

            original_ids.append(assignment.pk)

        preview = preview_storage_container_move(
            container=self.box,
            destination=self.freezer_b,
        )

        self.assertEqual(
            preview["active_sample_count"], 10
        )
        self.assertEqual(
            preview["active_assignment_count"], 10
        )
        self.assertEqual(
            preview["affected_location_count"], 1
        )

        self.box.refresh_from_db()
        self.assertEqual(
            self.box.parent_id,
            self.freezer_a.pk,
        )

        assignments = list(
            SampleStorageAssignment.objects
            .filter(pk__in=original_ids)
            .order_by("position")
        )

        self.assertEqual(
            [a.position for a in assignments],
            [f"P{i:02d}" for i in range(1, 11)],
        )

        self.assertTrue(
            all(
                a.location_id == self.box.pk
                for a in assignments
            )
        )
