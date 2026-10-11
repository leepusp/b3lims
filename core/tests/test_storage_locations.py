"""Regression tests for canonical Sample physical storage."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models.samples.sample import (
    Sample,
    SampleStorageLevel,
)
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.services.storage_locations import (
    assign_sample_storage_from_text,
    get_all_storage_paths,
    get_primary_storage_path,
    split_location_text,
)


class StorageLocationServiceTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username="storage-user",
                password="test-password",
            )
        )

        self.sample = Sample.objects.create(
            sample_id="STORAGE-001",
            sample_type="Other",
            organism_name="Storage test",
            owner=self.user,
        )

    def test_split_location_text_supports_multiple_paths(
        self,
    ):
        self.assertEqual(
            split_location_text(
                (
                    "Room 1 > Freezer A > Box 1; "
                    "Room 2, Freezer B, Box 2"
                )
            ),
            [
                [
                    "Room 1",
                    "Freezer A",
                    "Box 1",
                ],
                [
                    "Room 2",
                    "Freezer B",
                    "Box 2",
                ],
            ],
        )

    def test_assignment_materializes_canonical_hierarchy(
        self,
    ):
        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=(
                "Room 1 > Freezer A > "
                "Rack 01 > Box 001 > A01"
            ),
        )

        assignment = (
            SampleStorageAssignment.objects
            .select_related(
                "location"
            )
            .get(
                sample=self.sample
            )
        )

        self.assertTrue(
            assignment.is_primary
        )

        self.assertEqual(
            assignment.rank,
            1,
        )

        self.assertEqual(
            assignment.status,
            "active",
        )

        self.assertEqual(
            assignment.location.full_path,
            (
                "Room 1 > Freezer A > "
                "Rack 01 > Box 001 > A01"
            ),
        )

        self.assertEqual(
            StorageLocation.objects.count(),
            5,
        )

        self.assertEqual(
            set(
                StorageLocation.objects
                .values_list(
                    "location_type",
                    flat=True,
                )
            ),
            {
                "other",
            },
        )

    def test_legacy_storage_is_kept_in_sync(
        self,
    ):
        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=(
                "Room 1 > Freezer A > "
                "Rack 01 > Box 001 > A01"
            ),
        )

        self.sample.refresh_from_db()

        self.assertEqual(
            self.sample.storage_location,
            (
                "Room 1 > Freezer A > "
                "Rack 01 > Box 001 > A01"
            ),
        )

        self.assertEqual(
            list(
                SampleStorageLevel.objects
                .filter(
                    sample=self.sample
                )
                .order_by(
                    "level_index"
                )
                .values_list(
                    "name",
                    flat=True,
                )
            ),
            [
                "Room 1",
                "Freezer A",
                "Rack 01",
                "Box 001",
                "A01",
            ],
        )

    def test_repeated_assignment_reuses_location_nodes(
        self,
    ):
        location_text = (
            "Room 1 > Freezer A > Box 001"
        )

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=location_text,
        )

        initial_location_count = (
            StorageLocation.objects.count()
        )

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=location_text,
        )

        self.assertEqual(
            StorageLocation.objects.count(),
            initial_location_count,
        )

        self.assertEqual(
            SampleStorageAssignment.objects
            .filter(
                sample=self.sample
            )
            .count(),
            1,
        )

    def test_multiple_paths_create_ranked_assignments(
        self,
    ):
        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=(
                "Room 1 > Freezer A > Box 1; "
                "Room 2 > Freezer B > Box 2"
            ),
        )

        assignments = list(
            SampleStorageAssignment.objects
            .filter(
                sample=self.sample
            )
            .select_related(
                "location"
            )
            .order_by(
                "rank"
            )
        )

        self.assertEqual(
            len(assignments),
            2,
        )

        self.assertEqual(
            [
                row.rank
                for row
                in assignments
            ],
            [
                1,
                2,
            ],
        )

        self.assertEqual(
            [
                row.is_primary
                for row
                in assignments
            ],
            [
                True,
                False,
            ],
        )

        self.assertEqual(
            get_all_storage_paths(
                self.sample
            ),
            [
                (
                    "Room 1 > Freezer A > "
                    "Box 1"
                ),
                (
                    "Room 2 > Freezer B > "
                    "Box 2"
                ),
            ],
        )

        self.assertEqual(
            get_primary_storage_path(
                self.sample
            ),
            (
                "Room 1 > Freezer A > Box 1"
            ),
        )

    def test_empty_location_clears_assignments_and_legacy_state(
        self,
    ):
        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=(
                "Room 1 > Freezer A"
            ),
        )

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text="",
        )

        self.sample.refresh_from_db()

        self.assertFalse(
            SampleStorageAssignment.objects
            .filter(
                sample=self.sample
            )
            .exists()
        )

        self.assertFalse(
            SampleStorageLevel.objects
            .filter(
                sample=self.sample
            )
            .exists()
        )

        self.assertEqual(
            self.sample.storage_location,
            "",
        )
