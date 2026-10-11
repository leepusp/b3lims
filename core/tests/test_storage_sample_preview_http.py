from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
)


class StorageSamplePreviewHTTPTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="d3-http-owner"
        )
        cls.other = User.objects.create_user(
            username="d3-http-other"
        )

        cls.room = StorageLocation.objects.create(
            name="D3 HTTP Room",
            location_type="room",
        )
        cls.box_a = StorageLocation.objects.create(
            name="D3 HTTP Box A",
            parent=cls.room,
            location_type="box",
        )
        cls.box_b = StorageLocation.objects.create(
            name="D3 HTTP Box B",
            parent=cls.room,
            location_type="box",
        )

        cls.sample = Sample.objects.create(
            sample_id="D3-HTTP-VISIBLE",
            sample_type="Other",
            organism_name="Visible Sample",
            owner=cls.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        cls.private_sample = Sample.objects.create(
            sample_id="D3-HTTP-PRIVATE",
            sample_type="Other",
            organism_name="Private Sample",
            owner=cls.other,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        cls.assignment = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.box_a,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )

        cls.private_assignment = (
            SampleStorageAssignment.objects.create(
                sample=cls.private_sample,
                location=cls.box_b,
                rank=1,
                is_primary=True,
                position="P02",
                status="active",
            )
        )

    def preview(self, assignment_id, destination_id, position):
        return self.client.get(
            reverse("storage_workspace"),
            {
                "preview_sample": "1",
                "assignment_id": str(assignment_id),
                "destination_id": str(destination_id),
                "position": position,
            },
        )

    def test_form_lists_only_editable_assignments(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="storage-sample-preview"')
        self.assertContains(response, "D3-HTTP-VISIBLE")
        self.assertNotContains(response, "D3-HTTP-PRIVATE")
        self.assertIsNone(
            response.context["storage_sample_preview"]
        )

    def test_valid_preview_is_read_only(self):
        self.client.force_login(self.owner)

        before = (
            self.assignment.location_id,
            self.assignment.position,
        )

        response = self.preview(
            self.assignment.pk,
            self.box_b.pk,
            "P04",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Preview only — no Sample transferred.",
        )

        result = response.context["storage_sample_preview"]

        self.assertEqual(result["affected_assignment_count"], 1)
        self.assertEqual(result["moves"][0]["position_after"], "P04")
        self.assertEqual(
            result["moves"][0]["destination_path"],
            self.box_b.full_path,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            (
                self.assignment.location_id,
                self.assignment.position,
            ),
            before,
        )

        self.assertFalse(StorageMovement.objects.exists())

    def test_foreign_assignment_is_forbidden(self):
        self.client.force_login(self.owner)

        response = self.preview(
            self.private_assignment.pk,
            self.box_a.pk,
            "P09",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageMovement.objects.exists())

    def test_occupied_position_does_not_disclose_occupant(self):
        self.client.force_login(self.owner)

        response = self.preview(
            self.assignment.pk,
            self.box_b.pk,
            "P02",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Destination position is occupied.",
        )
        self.assertNotContains(
            response,
            "D3-HTTP-PRIVATE",
        )
        self.assertIsNone(
            response.context["storage_sample_preview"]
        )

    def test_invalid_assignment_identifier(self):
        self.client.force_login(self.owner)

        response = self.preview(
            "invalid",
            self.box_b.pk,
            "P04",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Invalid Sample transfer selection.",
        )
        self.assertIsNone(
            response.context["storage_sample_preview"]
        )

    def test_inactive_hierarchy_rejected(self):
        self.client.force_login(self.owner)

        self.room.is_active = False
        self.room.save(update_fields=["is_active"])

        response = self.preview(
            self.assignment.pk,
            self.box_b.pk,
            "P04",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Source or destination hierarchy is inactive.",
        )
        self.assertFalse(StorageMovement.objects.exists())
