from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.sample import Sample, SampleStorageLevel
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
)
from core.services.storage_registration_v8 import (
    register_initial_physical_storage,
)


class PhysicalStorageRegistrationV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ccalomeno",
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

    def sample(self, code, path=""):
        return Sample.objects.create(
            sample_id=code,
            sample_type="Other",
            organism_name="Storage V8 Test",
            owner=self.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=path,
        )

    def register(self, sample, position, mode="new", expected=""):
        return register_initial_physical_storage(
            sample=sample,
            box=self.box,
            position=position,
            actor=self.user,
            mode=mode,
            expected_legacy_path=expected,
        )

    def test_new_sample_keeps_position_and_audit(self):
        sample = self.sample("V8-NEW")

        assignment, movement = self.register(sample, "A1")

        sample.refresh_from_db()

        self.assertEqual(assignment.position, "A1")
        self.assertEqual(
            sample.storage_location,
            "Freezer Regina > Caixa 1.1 > A1",
        )
        self.assertEqual(movement.movement_type, "registration")
        self.assertEqual(movement.items.count(), 1)

        levels = list(
            SampleStorageLevel.objects.filter(sample=sample)
            .order_by("level_index")
            .values_list("name", flat=True)
        )
        self.assertEqual(
            levels,
            ["Freezer Regina", "Caixa 1.1", "A1"],
        )

    def test_reconcile_historical_sample_without_movement(self):
        path = "Freezer Regina > Caixa 1.1 > B5"
        sample = self.sample("V8-HISTORICAL", path)

        assignment, movement = self.register(
            sample,
            "B5",
            mode="historical",
            expected=path,
        )

        sample.refresh_from_db()

        self.assertEqual(sample.storage_location, path)
        self.assertEqual(assignment.location_id, self.box.pk)
        self.assertEqual(assignment.position, "B5")
        self.assertEqual(movement.movement_type, "registration")
        self.assertEqual(movement.origin_path, path)
        self.assertEqual(movement.destination_path, path)

    def test_occupied_position_is_rejected(self):
        first = self.sample("V8-FIRST")
        second = self.sample("V8-SECOND")

        self.register(first, "A2")

        with self.assertRaises(ValidationError):
            self.register(second, "A2")

        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=second
            ).exists()
        )

    def test_stale_historical_path_is_rejected(self):
        sample = self.sample(
            "V8-STALE",
            "Freezer Chuck > Caixa 1.2 > B5",
        )

        with self.assertRaises(ValidationError):
            self.register(
                sample,
                "B5",
                mode="historical",
                expected="Freezer Chuck > Caixa 1.2 > B5",
            )

    def test_idempotent_retry_creates_no_duplicate_audit(self):
        sample = self.sample("V8-RETRY")
        first, movement = self.register(sample, "A3")

        sample.refresh_from_db()

        second, retry_movement = self.register(
            sample,
            "A3",
            mode="historical",
            expected=sample.storage_location,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertIsNone(retry_movement)
        self.assertEqual(
            StorageMovement.objects.filter(
                movement_type="registration",
            ).count(),
            1,
        )

    def test_inactive_box_is_rejected(self):
        sample = self.sample("V8-INACTIVE")
        self.box.is_active = False
        self.box.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.register(sample, "A4")
