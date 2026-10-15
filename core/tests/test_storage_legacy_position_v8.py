from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models.samples.sample import (
    Sample,
    SampleStorageLevel,
)
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_legacy_sync import (
    sync_primary_storage_legacy_for_samples,
)
from core.services.storage_registration_v8 import (
    register_initial_physical_storage,
)


class PhysicalPositionLegacySyncV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="storage-position-v8",
            is_staff=True,
        )
        cls.freezer = StorageLocation.objects.create(
            name="Freezer Regina",
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Caixa 1.1",
            location_type="box",
            parent=cls.freezer,
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="V8 Position Synchronization Workspace",
            scope="personal",
            owner=cls.user,
        )

        StorageLocation.objects.filter(
            pk__in=[cls.freezer.pk, cls.box.pk]
        ).update(workspace=cls.workspace)

    def create_sample(self, code):
        return Sample.objects.create(
            sample_id=code,
            sample_type="Other",
            organism_name="Storage Position Test",
            owner=self.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location="",
        )

    def get_levels(self, sample):
        return list(
            SampleStorageLevel.objects
            .filter(sample=sample)
            .order_by("level_index", "pk")
            .values_list("name", flat=True)
        )

    def test_position_remains_in_legacy_path_after_sync(self):
        sample = self.create_sample("V8-SYNC-B5")

        register_initial_physical_storage(
            sample=sample,
            box=self.box,
            position="B5",
            actor=self.user,
            mode="new",
            expected_legacy_path="",
        )

        # Simulate legacy fields becoming stale while the canonical
        # assignment remains correct.
        Sample.objects.filter(pk=sample.pk).update(
            storage_location="OLD VALUE"
        )

        count = sync_primary_storage_legacy_for_samples(
            sample_ids={sample.pk}
        )

        sample.refresh_from_db()

        self.assertEqual(count, 1)
        self.assertEqual(
            sample.storage_location,
            "Freezer Regina > Caixa 1.1 > B5",
        )
        self.assertEqual(
            self.get_levels(sample),
            ["Freezer Regina", "Caixa 1.1", "B5"],
        )

    def test_resync_does_not_duplicate_position(self):
        sample = self.create_sample("V8-SYNC-IDEMPOTENT")

        register_initial_physical_storage(
            sample=sample,
            box=self.box,
            position="C3",
            actor=self.user,
            mode="new",
            expected_legacy_path="",
        )

        sync_primary_storage_legacy_for_samples(
            sample_ids={sample.pk}
        )
        sync_primary_storage_legacy_for_samples(
            sample_ids={sample.pk}
        )

        sample.refresh_from_db()

        self.assertEqual(
            sample.storage_location,
            "Freezer Regina > Caixa 1.1 > C3",
        )
        self.assertEqual(
            self.get_levels(sample),
            ["Freezer Regina", "Caixa 1.1", "C3"],
        )

    def test_unslotted_assignment_remains_compatible(self):
        sample = self.create_sample("V8-SYNC-NO-SLOT")

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=self.box,
            rank=1,
            is_primary=True,
            status="active",
            position="",
        )

        sync_primary_storage_legacy_for_samples(
            sample_ids={sample.pk}
        )

        sample.refresh_from_db()

        self.assertEqual(
            sample.storage_location,
            "Freezer Regina > Caixa 1.1",
        )

    def test_existing_position_node_is_not_duplicated(self):
        sample = self.create_sample("V8-LEGACY-NODE")

        position_node = StorageLocation.objects.create(
            name="A9",
            location_type="position",
            parent=self.box,
        )

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=position_node,
            rank=1,
            is_primary=True,
            status="active",
            position="A9",
        )

        sync_primary_storage_legacy_for_samples(
            sample_ids={sample.pk}
        )

        sample.refresh_from_db()

        self.assertEqual(
            sample.storage_location,
            "Freezer Regina > Caixa 1.1 > A9",
        )

    def test_conflicting_position_node_is_rejected(self):
        sample = self.create_sample("V8-CONFLICT-NODE")

        position_node = StorageLocation.objects.create(
            name="A9",
            location_type="position",
            parent=self.box,
        )

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=position_node,
            rank=1,
            is_primary=True,
            status="active",
            position="B5",
        )

        with self.assertRaises(ValidationError):
            sync_primary_storage_legacy_for_samples(
                sample_ids={sample.pk}
            )

        sample.refresh_from_db()
        self.assertEqual(sample.storage_location, "")

    def test_database_prevents_case_insensitive_slot_collision(self):
        first = self.create_sample("V8-SLOT-ONE")
        second = self.create_sample("V8-SLOT-TWO")

        SampleStorageAssignment.objects.create(
            sample=first,
            location=self.box,
            rank=1,
            is_primary=True,
            status="active",
            position="B5",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SampleStorageAssignment.objects.create(
                    sample=second,
                    location=self.box,
                    rank=1,
                    is_primary=True,
                    status="active",
                    position="b5",
                )

        self.assertFalse(
            SampleStorageAssignment.objects
            .filter(sample=second)
            .exists()
        )
