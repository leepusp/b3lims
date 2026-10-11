from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.sample import (
    Sample,
    SampleStorageLevel,
)
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
)
from core.services.storage_container_movements import (
    move_storage_container,
)
from core.services.storage_locations import (
    _sync_legacy_storage_levels,
    get_all_storage_paths,
)


class StorageLegacySynchronizationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(
            username="storage-c2-manager",
            is_staff=True,
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
        cls.shelf = StorageLocation.objects.create(
            name="Prateleira",
            parent=cls.freezer_a,
            location_type="shelf",
        )

        cls.sample_a = Sample.objects.create(
            sample_id="C2-001",
            sample_type="Other",
            organism_name="C2 Sample A",
            owner=cls.manager,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=cls.box.full_path,
        )

        cls.sample_b = Sample.objects.create(
            sample_id="C2-002",
            sample_type="Other",
            organism_name="C2 Sample B",
            owner=cls.manager,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=cls.shelf.full_path,
        )

        # A: primary inside the box; secondary outside.
        SampleStorageAssignment.objects.create(
            sample=cls.sample_a,
            location=cls.box,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )
        SampleStorageAssignment.objects.create(
            sample=cls.sample_a,
            location=cls.shelf,
            rank=2,
            is_primary=False,
            position="E01",
            status="active",
        )

        # B: primary outside the box; secondary inside.
        SampleStorageAssignment.objects.create(
            sample=cls.sample_b,
            location=cls.shelf,
            rank=1,
            is_primary=True,
            position="E02",
            status="active",
        )
        SampleStorageAssignment.objects.create(
            sample=cls.sample_b,
            location=cls.box,
            rank=2,
            is_primary=False,
            position="P02",
            status="active",
        )

        _sync_legacy_storage_levels(
            cls.sample_a,
            cls.box.full_path_parts,
        )
        _sync_legacy_storage_levels(
            cls.sample_b,
            cls.shelf.full_path_parts,
        )

    def move(self, destination=None):
        return move_storage_container(
            container=self.box,
            destination=destination or self.freezer_b,
            actor=self.manager,
            expected_parent_id=self.freezer_a.pk,
            reason="C2 compatibility validation",
        )

    def test_primary_and_secondary_paths_are_consistent(self):
        before = list(
            SampleStorageAssignment.objects
            .order_by("pk")
            .values_list(
                "pk",
                "sample_id",
                "location_id",
                "rank",
                "is_primary",
                "position",
                "status",
            )
        )

        movement = self.move()

        self.sample_a.refresh_from_db()
        self.sample_b.refresh_from_db()

        new_path = "Sala A > Freezer B > Caixa Y"
        shelf_path = "Sala A > Freezer A > Prateleira"

        self.assertEqual(
            self.sample_a.storage_location,
            new_path,
        )
        self.assertEqual(
            self.sample_b.storage_location,
            shelf_path,
        )

        self.assertEqual(
            get_all_storage_paths(self.sample_a),
            [new_path, shelf_path],
        )
        self.assertEqual(
            get_all_storage_paths(self.sample_b),
            [shelf_path, new_path],
        )

        levels = list(
            SampleStorageLevel.objects
            .filter(sample=self.sample_a)
            .order_by("level_index")
            .values_list("name", flat=True)
        )

        self.assertEqual(
            levels,
            ["Sala A", "Freezer B", "Caixa Y"],
        )

        after = list(
            SampleStorageAssignment.objects
            .order_by("pk")
            .values_list(
                "pk",
                "sample_id",
                "location_id",
                "rank",
                "is_primary",
                "position",
                "status",
            )
        )

        self.assertEqual(before, after)
        self.assertEqual(movement.items.count(), 2)

    def test_legacy_update_does_not_create_transfer_event(self):
        Event = apps.get_model("core", "Event")

        before = Event.objects.filter(
            sample_id__in=[
                self.sample_a.pk,
                self.sample_b.pk,
            ],
            event_type="transfer",
        ).count()

        self.move()

        after = Event.objects.filter(
            sample_id__in=[
                self.sample_a.pk,
                self.sample_b.pk,
            ],
            event_type="transfer",
        ).count()

        self.assertEqual(before, after)

    def test_path_overflow_rolls_back_movement(self):
        long_freezer = StorageLocation.objects.create(
            name="F" * 120,
            parent=self.room,
            location_type="freezer",
        )
        long_rack = StorageLocation.objects.create(
            name="R" * 120,
            parent=long_freezer,
            location_type="rack",
        )

        with self.assertRaises(ValidationError):
            self.move(destination=long_rack)

        self.box.refresh_from_db()
        self.sample_a.refresh_from_db()

        self.assertEqual(
            self.box.parent_id,
            self.freezer_a.pk,
        )
        self.assertEqual(
            self.sample_a.storage_location,
            "Sala A > Freezer A > Caixa Y",
        )
        self.assertFalse(
            StorageMovement.objects.exists()
        )
