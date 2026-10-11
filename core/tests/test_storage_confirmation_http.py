"""HTTP regression tests for confirmed Storage Workspace transfers."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
)
from core.services.storage_movement_preview import preview_storage_container_move
from core.services.storage_sample_movement_preview import preview_sample_movements


class StorageConfirmationHTTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="e3-storage-manager",
            email="e3-manager@example.invalid",
            password="unused-secret",
        )
        cls.room = StorageLocation.objects.create(
            name="E3 Room", location_type="room",
        )
        cls.freezer_a = StorageLocation.objects.create(
            name="E3 Freezer A", location_type="freezer", parent=cls.room,
        )
        cls.freezer_b = StorageLocation.objects.create(
            name="E3 Freezer B", location_type="freezer", parent=cls.room,
        )
        cls.box_a = StorageLocation.objects.create(
            name="E3 Box A", location_type="box", parent=cls.freezer_a,
        )
        cls.box_b = StorageLocation.objects.create(
            name="E3 Box B", location_type="box", parent=cls.freezer_b,
        )
        cls.sample_a = Sample.objects.create(
            sample_id="E3-TEST-SAMPLE-A", sample_type="Other",
            organism_name="Storage confirmation test", owner=cls.user,
            status="qc", aliquot_count=1, is_active=True,
            is_public=False, is_embargoed=False, storage_location="",
        )
        cls.sample_b = Sample.objects.create(
            sample_id="E3-TEST-SAMPLE-B", sample_type="Other",
            organism_name="Storage confirmation test", owner=cls.user,
            status="qc", aliquot_count=1, is_active=True,
            is_public=False, is_embargoed=False, storage_location="",
        )
        cls.assignment_a = SampleStorageAssignment.objects.create(
            sample=cls.sample_a, location=cls.box_a, rank=1,
            is_primary=True, status="active", position="A01",
        )
        cls.assignment_b = SampleStorageAssignment.objects.create(
            sample=cls.sample_b, location=cls.box_a, rank=1,
            is_primary=True, status="active", position="A02",
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("storage_workspace")

    def single_payload(self, position="B01"):
        preview = preview_sample_movements(
            moves=[{
                "assignment_id": self.assignment_a.pk,
                "destination_id": self.box_b.pk,
                "position": position,
            }],
            actor=self.user,
        )
        change = preview["moves"][0]
        return {
            "action": "confirm_sample_move",
            "reason": "Authorized Sample transfer test",
            **{
                key: change[key]
                for key in (
                    "assignment_id", "destination_id", "expected_location_id",
                    "expected_position", "expected_source_path",
                    "expected_destination_path",
                )
            },
            "position": change["position_after"],
        }

    def bulk_payload(self):
        preview = preview_sample_movements(
            moves=[
                {"assignment_id": self.assignment_a.pk, "destination_id": self.box_b.pk, "position": "B01"},
                {"assignment_id": self.assignment_b.pk, "destination_id": self.box_b.pk, "position": "B02"},
            ],
            actor=self.user,
        )
        columns = (
            "assignment_id", "destination_id", "expected_location_id",
            "expected_position", "expected_source_path",
            "expected_destination_path",
        )
        payload = {
            "action": "confirm_bulk_sample_move",
            "reason": "Authorized bulk transfer test",
        }
        for name in columns:
            payload["bulk_" + name] = [row[name] for row in preview["moves"]]
        payload["bulk_position"] = [row["position_after"] for row in preview["moves"]]
        return payload

    def test_individual_confirmation_and_history(self):
        response = self.client.get(self.url, {
            "preview_sample": "1", "assignment_id": self.assignment_a.pk,
            "destination_id": self.box_b.pk, "position": "B01",
        })
        self.assertContains(response, 'value="confirm_sample_move"')
        response = self.client.post(self.url, self.single_payload())
        self.assertEqual(response.status_code, 302)
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_b.pk)
        self.assertEqual(self.assignment_a.position, "B01")
        self.assignment_b.refresh_from_db()
        self.assertEqual(self.assignment_b.location_id, self.box_a.pk)
        movement = StorageMovement.objects.get(movement_type="sample")
        self.assertEqual(movement.performed_by_id, self.user.pk)
        self.assertEqual(movement.reason, "Authorized Sample transfer test")
        self.assertEqual(movement.items.count(), 1)

    def test_missing_reason_and_stale_source_are_rejected(self):
        payload = self.single_payload()
        payload["reason"] = " "
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.assertFalse(StorageMovement.objects.exists())
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_a.pk)

        payload = self.single_payload()
        SampleStorageAssignment.objects.filter(pk=self.assignment_a.pk).update(position="A77")
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.assertFalse(StorageMovement.objects.exists())
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.position, "A77")

    def test_bulk_confirmation_is_atomic_and_audited(self):
        response = self.client.post(self.url, self.bulk_payload())
        self.assertEqual(response.status_code, 302)
        self.assignment_a.refresh_from_db()
        self.assignment_b.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_b.pk)
        self.assertEqual(self.assignment_b.location_id, self.box_b.pk)
        self.assertEqual(self.assignment_a.position, "B01")
        self.assertEqual(self.assignment_b.position, "B02")
        movement = StorageMovement.objects.get(movement_type="sample_bulk")
        self.assertEqual(movement.items.count(), 2)

    def test_bulk_conflicting_positions_roll_back(self):
        payload = self.bulk_payload()
        payload["bulk_position"] = ["B01", "B01"]
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.assignment_a.refresh_from_db()
        self.assignment_b.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_a.pk)
        self.assertEqual(self.assignment_b.location_id, self.box_a.pk)
        self.assertFalse(StorageMovement.objects.exists())

    def test_container_confirmation_preserves_positions(self):
        preview = preview_storage_container_move(
            container=self.box_a, destination=self.freezer_b,
        )
        payload = {
            "action": "confirm_container_move",
            "reason": "Authorized container move test",
            "container_id": self.box_a.pk,
            "destination_id": self.freezer_b.pk,
            "expected_parent_id": preview["expected_parent_id"],
            "expected_origin_path": preview["old_path"],
            "expected_destination_path": preview["new_path"],
        }
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.box_a.refresh_from_db()
        self.assertEqual(self.box_a.parent_id, self.freezer_b.pk)
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_a.pk)
        self.assertEqual(self.assignment_a.position, "A01")
        movement = StorageMovement.objects.get(movement_type="container")
        self.assertEqual(movement.items.count(), 2)

    def test_stale_container_preview_is_rejected(self):
        preview = preview_storage_container_move(
            container=self.box_a, destination=self.freezer_b,
        )
        payload = {
            "action": "confirm_container_move",
            "reason": "Stale container move",
            "container_id": self.box_a.pk,
            "destination_id": self.freezer_b.pk,
            "expected_parent_id": preview["expected_parent_id"],
            "expected_origin_path": preview["old_path"],
            "expected_destination_path": preview["new_path"],
        }
        StorageLocation.objects.filter(pk=self.box_a.pk).update(parent=self.room)
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.box_a.refresh_from_db()
        self.assertEqual(self.box_a.parent_id, self.room.pk)
        self.assertFalse(StorageMovement.objects.exists())


    def test_anonymous_confirmation_requires_login(self):
        """Anonymous requests cannot execute physical transfers."""
        from django.test import Client

        response = Client().post(
            self.url,
            self.single_payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(StorageMovement.objects.exists())
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_a.pk)

    def test_csrf_required_for_confirmed_transfer(self):
        """Authenticated transfers require a valid CSRF token."""
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(
            self.url,
            self.single_payload(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageMovement.objects.exists())
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_a.pk)

    def test_other_user_cannot_transfer_private_sample(self):
        """A valid preview payload grants no additional permissions."""
        from django.test import Client

        outsider = get_user_model().objects.create_user(
            username="e3-storage-outsider",
            password="unused-secret",
        )
        client = Client()
        client.force_login(outsider)

        response = client.post(
            self.url,
            self.single_payload(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageMovement.objects.exists())
        self.assignment_a.refresh_from_db()
        self.assertEqual(self.assignment_a.location_id, self.box_a.pk)
