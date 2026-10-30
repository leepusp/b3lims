"""HTTP regressions for V8.14.6B1 Sample storage movement."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageWorkspace,
)


class SampleStorageEditMoveV8146Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username="v8146b1-owner",
            is_staff=True,
        )

        cls.outsider = get_user_model().objects.create_user(
            username="v8146b1-outsider",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="V8146B1 Personal Storage",
            scope="personal",
            owner=cls.owner,
        )

        cls.room = StorageLocation.objects.create(
            name="V8146B1 Room",
            location_type="room",
            workspace=cls.workspace,
        )

        cls.source = StorageLocation.objects.create(
            name="BBAMS",
            location_type="other",
            workspace=cls.workspace,
            parent=cls.room,
        )

        cls.destination = StorageLocation.objects.create(
            name="Custom destination",
            location_type="other",
            workspace=cls.workspace,
            parent=cls.room,
        )

        cls.secondary_location = StorageLocation.objects.create(
            name="Secondary box",
            location_type="box",
            workspace=cls.workspace,
            parent=cls.room,
        )

        cls.sample = Sample.objects.create(
            sample_id="V8146B1-001",
            sample_type="Other",
            organism_name="Storage integration test",
            owner=cls.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=cls.source.full_path,
        )

        cls.primary = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.source,
            rank=1,
            is_primary=True,
            position="A1",
            status="active",
        )

        cls.secondary = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.secondary_location,
            rank=2,
            is_primary=False,
            position="B5",
            status="active",
        )

        cls.occupied_sample = Sample.objects.create(
            sample_id="V8146B1-002",
            sample_type="Other",
            organism_name="Occupied slot",
            owner=cls.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=cls.destination.full_path,
        )

        SampleStorageAssignment.objects.create(
            sample=cls.occupied_sample,
            location=cls.destination,
            rank=1,
            is_primary=True,
            position="C3",
            status="active",
        )

    def setUp(self):
        self.client.force_login(self.owner)

        self.edit_url = reverse(
            "sample_edit",
            args=[self.sample.pk],
        )

        self.move_url = reverse(
            "sample_storage_move_v8146",
            args=[self.sample.pk],
        )

    def payload(self, **overrides):
        payload = {
            "storage_move_assignment_v8146":
                str(self.primary.pk),
            "storage_move_destination_v8146":
                str(self.destination.pk),
            "storage_move_position_v8146": "C7",
            "storage_move_reason_v8146":
                "Controlled physical relocation.",
            "storage_move_expected_location_v8146":
                str(self.source.pk),
            "storage_move_expected_position_v8146": "A1",
            "storage_move_expected_source_path_v8146":
                self.source.full_path,
            "storage_move_expected_destination_path_v8146":
                self.destination.full_path,
        }
        payload.update(overrides)
        return payload

    def test_editor_excludes_structured_move_panel(self):
        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            'id="sample-physical-movement-v8146"',
        )

        self.assertContains(response, "BBAMS")
        self.assertNotContains(response, "Custom destination")
        self.assertContains(
            response, "Current registered physical storage"
        )
        self.assertContains(
            response,
            "storage_edit_move_v8146.js",
        )

    def test_move_audits_and_preserves_secondary(self):
        response = self.client.post(
            self.move_url,
            self.payload(),
        )

        self.assertEqual(response.status_code, 302)

        self.primary.refresh_from_db()
        self.secondary.refresh_from_db()

        self.assertEqual(
            self.primary.location_id,
            self.destination.pk,
        )
        self.assertEqual(self.primary.position, "C7")

        self.assertEqual(
            self.secondary.location_id,
            self.secondary_location.pk,
        )
        self.assertEqual(self.secondary.position, "B5")

        self.assertEqual(
            StorageMovement.objects.filter(
                movement_type="sample",
            ).count(),
            1,
        )

        movement = StorageMovement.objects.get(
            movement_type="sample"
        )

        self.assertEqual(movement.items.count(), 1)

    def test_occupied_position_is_rejected(self):
        response = self.client.post(
            self.move_url,
            self.payload(
                storage_move_position_v8146="C3",
            ),
        )

        self.assertEqual(response.status_code, 302)

        self.primary.refresh_from_db()

        self.assertEqual(
            self.primary.location_id,
            self.source.pk,
        )

        self.assertFalse(
            StorageMovement.objects.filter(
                movement_type="sample",
            ).exists()
        )

    def test_stale_source_path_is_rejected(self):
        response = self.client.post(
            self.move_url,
            self.payload(
                storage_move_expected_source_path_v8146=(
                    "outdated source path"
                ),
            ),
        )

        self.assertEqual(response.status_code, 302)

        self.primary.refresh_from_db()

        self.assertEqual(
            self.primary.location_id,
            self.source.pk,
        )

        self.assertFalse(
            StorageMovement.objects.filter(
                movement_type="sample",
            ).exists()
        )

    def test_non_editor_cannot_move_sample(self):
        self.client.force_login(self.outsider)

        response = self.client.post(
            self.move_url,
            self.payload(),
        )

        self.assertEqual(response.status_code, 403)

        self.primary.refresh_from_db()

        self.assertEqual(
            self.primary.location_id,
            self.source.pk,
        )
