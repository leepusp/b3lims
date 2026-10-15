from django.core.exceptions import ValidationError
from django.test import TestCase

from django.contrib.auth import get_user_model
from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_sample_intake_v8 import (
    prepare_storage_sample_intake_v8,
)


class StorageSampleIntakeV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.freezer = StorageLocation.objects.create(
            name="Freezer Regina",
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Caixa 1.1",
            parent=cls.freezer,
            location_type="box",
        )
        cls.rack = StorageLocation.objects.create(
            name="Rack 4",
            parent=cls.freezer,
            location_type="rack",
        )

        cls.user = get_user_model().objects.create_user(
            username="storage-intake-owner-v8",
        )
        cls.workspace = StorageWorkspace.objects.create(
            name="Intake Test Workspace",
            owner=cls.user,
            scope="personal",
        )
        StorageLocation.objects.filter(
            pk__in=[
                cls.freezer.pk,
                cls.box.pk,
                cls.rack.pk,
            ]
        ).update(workspace=cls.workspace)

    def prepare(self, **changes):
        args = {
            "mode": "physical",
            "storage_text": self.box.full_path,
            "anchor_id": str(self.box.pk),
            "positions": ["A1", "A2"],
            "expected_samples": 2,
            "actor": self.user,
        }
        args.update(changes)
        return prepare_storage_sample_intake_v8(**args)

    def test_registered_box_with_two_distinct_positions(self):
        plan = self.prepare()

        self.assertEqual(plan.mode, "physical")
        self.assertEqual(plan.initial_text, "")
        self.assertEqual(plan.target_id, self.box.pk)
        self.assertEqual(plan.positions, ("A1", "A2"))

    def test_rack_can_be_a_physical_position_host(self):
        plan = self.prepare(
            storage_text=self.rack.full_path,
            anchor_id=self.rack.pk,
            positions=["C7", "C8"],
        )

        self.assertEqual(plan.target_id, self.rack.pk)
        self.assertEqual(plan.positions, ("C7", "C8"))

    def test_changed_text_cannot_spoof_registered_anchor(self):
        with self.assertRaises(ValidationError):
            self.prepare(
                storage_text="Freezer Chuck > Caixa 1.2"
            )

    def test_duplicate_positions_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.prepare(positions=["B5", "b5"])

    def test_aliquot_count_must_match_position_count(self):
        with self.assertRaises(ValidationError):
            self.prepare(expected_samples=3)

    def test_free_text_does_not_create_physical_nodes(self):
        before = StorageLocation.objects.count()

        plan = self.prepare(
            mode="unverified",
            storage_text="New Freezer > New Box > B5",
            anchor_id="",
            positions=[],
        )

        self.assertEqual(plan.mode, "unverified")
        self.assertEqual(
            plan.initial_text,
            "New Freezer > New Box > B5",
        )
        self.assertIsNone(plan.target_id)
        self.assertEqual(StorageLocation.objects.count(), before)

    def test_unverified_path_cannot_claim_anchor_id(self):
        with self.assertRaises(ValidationError):
            self.prepare(
                mode="unverified",
                anchor_id=self.box.pk,
                positions=[],
            )

    def test_unassigned_registration_is_explicit(self):
        plan = self.prepare(
            mode="unassigned",
            storage_text="",
            anchor_id="",
            positions=[],
        )

        self.assertEqual(plan.initial_text, "")
        self.assertIsNone(plan.target_id)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.prepare(mode="invent_new_storage")

    def test_inactive_parent_blocks_assignment(self):
        self.freezer.is_active = False
        self.freezer.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.prepare()
