from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)


class StorageWorkspaceAssignmentSafetyTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="workspace-safety-owner",
            is_staff=True,
        )

        cls.room = StorageLocation.objects.create(
            name="Sala Workspace",
            location_type="room",
        )

        cls.box_a = StorageLocation.objects.create(
            name="Caixa A",
            location_type="box",
            parent=cls.room,
        )

        cls.box_b = StorageLocation.objects.create(
            name="Caixa B",
            location_type="box",
            parent=cls.room,
        )

        cls.shelf = StorageLocation.objects.create(
            name="Prateleira",
            location_type="shelf",
            parent=cls.room,
        )

        cls.sample = Sample.objects.create(
            sample_id="WORKSPACE-SAFETY-001",
            sample_type="Other",
            organism_name="Workspace Safety Sample",
            owner=cls.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=cls.box_a.full_path,
        )

        cls.primary = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.box_a,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )

        cls.secondary = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.shelf,
            rank=2,
            is_primary=False,
            position="S01",
            status="active",
        )

    def test_workspace_assignment_preserves_other_locations(self):
        self.client.force_login(self.user)

        original_primary_id = self.primary.pk
        original_secondary_id = self.secondary.pk

        response = self.client.post(
            reverse("storage_workspace"),
            {
                "action": "assign_sample",
                "sample_id": str(self.sample.pk),
                "location_id": str(self.box_b.pk),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.primary.refresh_from_db()
        self.secondary.refresh_from_db()

        self.assertEqual(
            self.primary.pk,
            original_primary_id,
        )
        self.assertEqual(
            self.primary.location_id,
            self.box_b.pk,
        )

        self.assertEqual(
            self.secondary.pk,
            original_secondary_id,
        )
        self.assertEqual(
            self.secondary.location_id,
            self.shelf.pk,
        )
        self.assertEqual(
            self.secondary.position,
            "S01",
        )
        self.assertEqual(
            self.secondary.rank,
            2,
        )

        self.assertEqual(
            SampleStorageAssignment.objects.filter(
                sample=self.sample,
                status="active",
            ).count(),
            2,
        )

    def test_workspace_primary_move_is_audited(self):
        from core.models.samples.storage import (
            StorageMovement,
        )

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("storage_workspace"),
            {
                "action": "assign_sample",
                "sample_id": str(self.sample.pk),
                "location_id": str(self.box_b.pk),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.primary.refresh_from_db()
        self.secondary.refresh_from_db()
        self.sample.refresh_from_db()

        self.assertEqual(
            self.primary.location_id,
            self.box_b.pk,
        )
        self.assertEqual(self.primary.position, "")
        self.assertEqual(self.secondary.position, "S01")
        self.assertEqual(
            self.sample.storage_location,
            self.box_b.full_path,
        )

        movement = StorageMovement.objects.get(
            movement_type="sample"
        )

        self.assertEqual(
            movement.items.count(),
            1,
        )

        item = movement.items.get()

        self.assertEqual(
            item.assignment_id_snapshot,
            self.primary.pk,
        )
        self.assertEqual(item.position_before, "P01")
        self.assertEqual(item.position_after, "")

    def test_workspace_rejects_duplicate_secondary_location(self):
        from core.models.samples.storage import StorageMovement

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("storage_workspace"),
            {
                "action": "assign_sample",
                "sample_id": str(self.sample.pk),
                "location_id": str(self.shelf.pk),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.primary.refresh_from_db()
        self.secondary.refresh_from_db()

        self.assertEqual(
            self.primary.location_id,
            self.box_a.pk,
        )
        self.assertEqual(
            self.secondary.location_id,
            self.shelf.pk,
        )
        self.assertEqual(
            self.secondary.position,
            "S01",
        )
        self.assertFalse(StorageMovement.objects.exists())
