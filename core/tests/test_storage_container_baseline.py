from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    StorageLocation,
    SampleStorageAssignment,
)
from core.services.storage_locations import get_all_storage_paths


class StorageContainerBaselineTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="storage-baseline-owner"
        )

        cls.room_x = StorageLocation.objects.create(
            name="Sala X",
            location_type="room",
        )
        cls.freezer_1 = StorageLocation.objects.create(
            name="Freezer 1",
            parent=cls.room_x,
            location_type="freezer",
        )
        cls.rack_a = StorageLocation.objects.create(
            name="Rack A",
            parent=cls.freezer_1,
            location_type="rack",
        )
        cls.box_y = StorageLocation.objects.create(
            name="Caixa Y",
            parent=cls.rack_a,
            location_type="box",
        )

        cls.room_z = StorageLocation.objects.create(
            name="Sala Z",
            location_type="room",
        )
        cls.freezer_2 = StorageLocation.objects.create(
            name="Freezer 2",
            parent=cls.room_z,
            location_type="freezer",
        )
        cls.rack_b = StorageLocation.objects.create(
            name="Rack B",
            parent=cls.freezer_2,
            location_type="rack",
        )

        cls.samples = []
        cls.assignments = []

        for index in range(1, 11):
            sample = Sample.objects.create(
                sample_id=f"STORAGE-TEST-{index:03d}",
                sample_type="Other",
                organism_name=f"Test Sample {index}",
                owner=cls.owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )

            assignment = SampleStorageAssignment.objects.create(
                sample=sample,
                location=cls.box_y,
                rank=1,
                is_primary=True,
                position=f"P{index:02d}",
                status="active",
            )

            cls.samples.append(sample)
            cls.assignments.append(assignment)

    def test_container_move_preserves_samples_and_positions(self):
        original = {
            a.pk: (a.sample_id, a.position, a.location_id)
            for a in self.assignments
        }

        self.box_y.parent = self.rack_b
        self.box_y.save(update_fields=["parent"])

        expected = (
            "Sala Z > Freezer 2 > Rack B > Caixa Y"
        )

        for sample, assignment in zip(
            self.samples, self.assignments
        ):
            assignment.refresh_from_db()

            self.assertEqual(
                (assignment.sample_id,
                 assignment.position,
                 assignment.location_id),
                original[assignment.pk],
            )

            self.assertEqual(
                get_all_storage_paths(sample),
                [expected],
            )

    def test_individual_sample_move_preserves_others(self):
        first = self.assignments[0]
        second = self.assignments[1]

        first.location = self.rack_b
        first.position = "P01"
        first.save(update_fields=["location", "position"])

        second.refresh_from_db()

        self.assertEqual(first.location_id, self.rack_b.pk)
        self.assertEqual(second.location_id, self.box_y.pk)
        self.assertEqual(second.position, "P02")
        self.assertEqual(self.box_y.parent_id, self.rack_a.pk)

    def test_nested_rack_move_preserves_box_contents(self):
        self.rack_a.parent = self.freezer_2
        self.rack_a.save(update_fields=["parent"])

        expected = (
            "Sala Z > Freezer 2 > Rack A > Caixa Y"
        )

        for sample, assignment in zip(
            self.samples, self.assignments
        ):
            assignment.refresh_from_db()

            self.assertEqual(
                assignment.location_id,
                self.box_y.pk,
            )

            self.assertEqual(
                get_all_storage_paths(sample),
                [expected],
            )
