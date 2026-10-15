from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.services.storage_anchor_v8 import (
    validate_storage_anchor_plan,
)


class StorageAnchorV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="storage-anchor-v8",
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

    def plan(self, positions, **kwargs):
        return validate_storage_anchor_plan(
            mode=kwargs.get("mode", "physical"),
            box_id=kwargs.get("box_id", self.box.pk),
            positions=positions,
            expected_samples=kwargs.get(
                "expected_samples",
                len(positions),
            ),
        )

    def test_registered_anchors_are_resolved(self):
        plan = self.plan(["a1", "a2"])

        self.assertEqual(plan.box_id, self.box.pk)
        self.assertEqual(
            plan.box_path,
            "Freezer Regina > Caixa 1.1",
        )
        self.assertEqual(plan.positions, ("A1", "A2"))

    def test_duplicate_positions_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.plan(["B5", "b5"])

    def test_position_count_must_match_samples(self):
        with self.assertRaises(ValidationError):
            self.plan(["A1"], expected_samples=3)

    def test_inactive_freezer_is_rejected(self):
        self.freezer.is_active = False
        self.freezer.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.plan(["A1"])

    def test_unknown_box_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.plan(["A1"], box_id=99999999)

    def test_existing_occupancy_is_rejected(self):
        sample = Sample.objects.create(
            sample_id="ANCHOR-EXISTING",
            sample_type="Other",
            organism_name="Storage Anchor Test",
            owner=self.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=self.box,
            rank=1,
            is_primary=True,
            position="B5",
            status="active",
        )

        with self.assertRaises(ValidationError):
            self.plan(["b5"])

    def test_unassigned_is_explicit(self):
        plan = validate_storage_anchor_plan(
            mode="unassigned",
            box_id="",
            positions=[],
            expected_samples=2,
        )

        self.assertIsNone(plan.box_id)
        self.assertEqual(plan.positions, ())
