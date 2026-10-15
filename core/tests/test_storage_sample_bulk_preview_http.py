from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
    StorageMovement,
)


class StorageSampleBulkPreviewHTTPTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="d3-bulk-owner"
        )
        cls.other = User.objects.create_user(
            username="d3-bulk-other"
        )

        cls.room = StorageLocation.objects.create(
            name="D3 Bulk Room",
            location_type="room",
        )
        cls.box_a = StorageLocation.objects.create(
            name="D3 Bulk Box A",
            parent=cls.room,
            location_type="box",
        )
        cls.box_b = StorageLocation.objects.create(
            name="D3 Bulk Box B",
            parent=cls.room,
            location_type="box",
        )

        assignments = []

        for i, (owner, box, position) in enumerate((
            (cls.owner, cls.box_a, "P01"),
            (cls.owner, cls.box_a, "P02"),
            (cls.other, cls.box_b, "P09"),
        ), 1):
            sample = Sample.objects.create(
                sample_id=f"D3-BULK-{i}",
                sample_type="Other",
                organism_name=f"D3 Bulk Sample {i}",
                owner=owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )

            assignments.append(
                SampleStorageAssignment.objects.create(
                    sample=sample,
                    location=box,
                    rank=1,
                    is_primary=True,
                    position=position,
                    status="active",
                )
            )

        cls.first, cls.second, cls.private = assignments

        cls.workspace = StorageWorkspace.objects.create(
            name="D3 Bulk Preview Workspace",
            scope="personal",
            owner=cls.owner,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.room.pk,
                cls.box_a.pk,
                cls.box_b.pk,
            ]
        ).update(workspace=cls.workspace)

    def preview(self, rows):
        return self.client.get(
            reverse("storage_workspace"),
            {
                "preview_bulk_samples": "1",
                "bulk_assignment_id": [
                    str(row[0]) for row in rows
                ],
                "bulk_destination_id": [
                    str(row[1]) for row in rows
                ],
                "bulk_position": [
                    row[2] for row in rows
                ],
            },
        )

    def test_form_is_visible_with_only_editable_samples(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="storage-sample-bulk-preview"',
        )
        self.assertContains(response, "D3-BULK-1")
        self.assertContains(response, "D3-BULK-2")
        self.assertNotContains(response, "D3-BULK-3")
        self.assertIsNone(
            response.context["storage_sample_bulk_preview"]
        )

    def test_two_selected_transfers_are_read_only(self):
        self.client.force_login(self.owner)

        response = self.preview([
            (self.first.pk, self.box_b.pk, "P04"),
            (self.second.pk, self.box_b.pk, "P05"),
        ])

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Bulk preview only — no transfers executed.",
        )

        result = response.context[
            "storage_sample_bulk_preview"
        ]

        self.assertEqual(result["affected_sample_count"], 2)
        self.assertEqual(result["affected_assignment_count"], 2)
        self.assertEqual(len(result["moves"]), 2)

        self.first.refresh_from_db()
        self.second.refresh_from_db()

        self.assertEqual(self.first.location_id, self.box_a.pk)
        self.assertEqual(self.first.position, "P01")
        self.assertEqual(self.second.location_id, self.box_a.pk)
        self.assertEqual(self.second.position, "P02")
        self.assertFalse(StorageMovement.objects.exists())

        # V89A5B_HTTP_ASSERTIONS: authorized preview visibility
        self.assertContains(response, 'data-b3-v89-movement-comparison="bulk"', count=1)
        self.assertContains(response, 'data-b3-v89-movement-row', count=2)
        self.assertContains(response, 'data-b3-v89-path-before', count=2)
        self.assertContains(response, 'data-b3-v89-path-after', count=2)

    def test_selected_positions_can_be_swapped(self):
        self.client.force_login(self.owner)

        response = self.preview([
            (self.first.pk, self.box_a.pk, "P02"),
            (self.second.pk, self.box_a.pk, "P01"),
        ])

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(
            response.context["storage_sample_bulk_preview"]
        )
        self.assertFalse(StorageMovement.objects.exists())

    def test_collision_invalidates_entire_preview(self):
        self.client.force_login(self.owner)

        response = self.preview([
            (self.first.pk, self.box_b.pk, "P04"),
            (self.second.pk, self.box_b.pk, "p04"),
        ])

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Multiple transfers target the same position.",
        )
        self.assertIsNone(
            response.context["storage_sample_bulk_preview"]
        )
        self.assertFalse(StorageMovement.objects.exists())

    def test_foreign_assignment_denies_entire_batch(self):
        self.client.force_login(self.owner)

        response = self.preview([
            (self.first.pk, self.box_b.pk, "P04"),
            (self.private.pk, self.box_a.pk, "P08"),
        ])

        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageMovement.objects.exists())

        # V89A5B_HTTP_ASSERTIONS: authorized preview visibility
        self.assertNotContains(response, 'data-b3-v89-movement-comparison=', status_code=403)

    def test_hidden_occupied_slot_does_not_reveal_sample(self):
        self.client.force_login(self.owner)

        response = self.preview([
            (self.first.pk, self.box_b.pk, "P09"),
        ])

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Destination position is occupied.",
        )
        self.assertNotContains(response, "D3-BULK-3")
        self.assertIsNone(
            response.context["storage_sample_bulk_preview"]
        )

        # V89A5B_HTTP_ASSERTIONS: authorized preview visibility
        self.assertNotContains(response, 'data-b3-v89-movement-comparison=')

    def test_incomplete_row_is_rejected(self):
        self.client.force_login(self.owner)

        response = self.preview([
            (self.first.pk, "", "P04"),
        ])

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Each selected row needs a valid assignment",
        )
        self.assertIsNone(
            response.context["storage_sample_bulk_preview"]
        )

    def test_more_than_five_rows_is_rejected(self):
        self.client.force_login(self.owner)

        rows = [
            (self.first.pk, self.box_b.pk, f"P{i:02d}")
            for i in range(6)
        ]

        response = self.preview(rows)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Invalid bulk preview fields.",
        )
        self.assertIsNone(
            response.context["storage_sample_bulk_preview"]
        )
