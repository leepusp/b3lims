"""Regression tests for idempotent Storage initialization."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import SampleStorageAssignment
from core.services.storage_locations import (
    assign_sample_storage_from_text,
)


class StorageAssignmentIdempotencyTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        owner = get_user_model().objects.create_user(
            username="e2-idempotency-owner",
        )

        cls.sample = Sample.objects.create(
            sample_id="E2-IDEMPOTENCY-001",
            sample_type="Other",
            organism_name="Storage Idempotency Test",
            owner=owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location="",
        )

    def test_repeated_primary_path_preserves_assignment(self):
        path = "E2 Room > Freezer A > Box 1"

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=path,
        )

        assignment = SampleStorageAssignment.objects.get(
            sample=self.sample,
        )
        original_id = assignment.pk

        SampleStorageAssignment.objects.filter(
            pk=original_id,
        ).update(
            position="P01",
            container_type="Cryovial",
        )

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=path,
        )

        rows = list(
            SampleStorageAssignment.objects.filter(
                sample=self.sample,
            )
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pk, original_id)
        self.assertEqual(rows[0].position, "P01")
        self.assertEqual(rows[0].container_type, "Cryovial")
        self.assertTrue(rows[0].is_primary)

    def test_repeated_multiple_paths_preserves_secondary(self):
        paths = (
            "E2 Room > Freezer A > Box 1; "
            "E2 Room > Freezer B > Box 2"
        )

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=paths,
        )

        original_ids = list(
            SampleStorageAssignment.objects
            .filter(sample=self.sample)
            .order_by("rank")
            .values_list("pk", flat=True)
        )

        SampleStorageAssignment.objects.filter(
            pk=original_ids[1],
        ).update(
            position="S07",
            container_type="Cryovial",
        )

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=paths,
        )

        rows = list(
            SampleStorageAssignment.objects
            .filter(sample=self.sample)
            .order_by("rank")
        )

        self.assertEqual(
            [row.pk for row in rows],
            original_ids,
        )
        self.assertEqual(rows[1].position, "S07")
        self.assertEqual(rows[1].container_type, "Cryovial")
        self.assertFalse(rows[1].is_primary)


    def test_changed_path_rejects_positioned_assignment(self):
        """A physical slot cannot be removed by legacy replacement."""
        from django.core.exceptions import ValidationError

        original_path = "E2 Safety Room > Freezer A > Box 1"
        new_path = "E2 Safety Room > Freezer B > Box 2"

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=original_path,
        )

        assignment = SampleStorageAssignment.objects.get(
            sample=self.sample,
        )

        SampleStorageAssignment.objects.filter(
            pk=assignment.pk,
        ).update(position="P09")

        with self.assertRaisesRegex(
            ValidationError,
            "audited movement",
        ):
            assign_sample_storage_from_text(
                sample=self.sample,
                storage_location_text=new_path,
            )

        original = SampleStorageAssignment.objects.get(
            sample=self.sample,
        )

        self.assertEqual(original.pk, assignment.pk)
        self.assertEqual(original.position, "P09")
        self.assertEqual(original.location.full_path, original_path)

    def test_clear_rejects_existing_container_metadata(self):
        """Legacy clearing must not discard container metadata."""
        from decimal import Decimal
        from django.core.exceptions import ValidationError

        path = "E2 Safety Room > Freezer C > Box 3"

        assign_sample_storage_from_text(
            sample=self.sample,
            storage_location_text=path,
        )

        assignment = SampleStorageAssignment.objects.get(
            sample=self.sample,
        )

        SampleStorageAssignment.objects.filter(
            pk=assignment.pk,
        ).update(
            position="",
            container_type="Cryovial",
            quantity=Decimal("2.500"),
            quantity_unit="mL",
        )

        with self.assertRaisesRegex(
            ValidationError,
            "audited movement",
        ):
            assign_sample_storage_from_text(
                sample=self.sample,
                storage_location_text="",
            )

        original = SampleStorageAssignment.objects.get(
            sample=self.sample,
        )

        self.assertEqual(original.pk, assignment.pk)
        self.assertEqual(original.container_type, "Cryovial")
        self.assertEqual(original.quantity, Decimal("2.500"))
        self.assertEqual(original.quantity_unit, "mL")
        self.assertEqual(original.location.full_path, path)
