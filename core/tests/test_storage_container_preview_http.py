from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
)


class StorageContainerPreviewHTTPTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.manager = User.objects.create_user(
            username="d2-manager",
            is_staff=True,
        )
        cls.viewer = User.objects.create_user(
            username="d2-viewer",
        )

        cls.room_a = StorageLocation.objects.create(
            name="D2 Room A",
            location_type="room",
        )
        cls.room_b = StorageLocation.objects.create(
            name="D2 Room B",
            location_type="room",
        )
        cls.shelf_a = StorageLocation.objects.create(
            name="Shelf A",
            parent=cls.room_a,
            location_type="shelf",
        )
        cls.shelf_b = StorageLocation.objects.create(
            name="Shelf B",
            parent=cls.room_b,
            location_type="shelf",
        )
        cls.box = StorageLocation.objects.create(
            name="Box X",
            parent=cls.shelf_a,
            location_type="box",
        )
        cls.position = StorageLocation.objects.create(
            name="Position 1",
            parent=cls.shelf_b,
            location_type="position",
        )

        cls.sample = Sample.objects.create(
            sample_id="D2-SAMPLE-001",
            sample_type="Other",
            organism_name="D2 sample",
            owner=cls.viewer,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        cls.assignment = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.box,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )

    def preview(self, user, container, destination):
        self.client.force_login(user)
        return self.client.get(
            reverse("storage_workspace"),
            {
                "preview_container": "1",
                "container_id": str(container),
                "destination_id": str(destination),
            },
        )

    def test_manager_preview_is_read_only(self):
        original_parent = self.box.parent_id
        original_assignment = (
            self.assignment.location_id,
            self.assignment.position,
        )

        response = self.preview(
            self.manager,
            self.box.pk,
            self.shelf_b.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Move Container")
        self.assertContains(
            response,
            "Preview only — no transfer executed.",
        )

        result = response.context["storage_container_preview"]

        self.assertEqual(
            result["old_path"],
            "D2 Room A > Shelf A > Box X",
        )
        self.assertEqual(
            result["new_path"],
            "D2 Room B > Shelf B > Box X",
        )
        self.assertEqual(result["active_sample_count"], 1)
        self.assertEqual(result["active_assignment_count"], 1)

        self.box.refresh_from_db()
        self.assignment.refresh_from_db()

        self.assertEqual(self.box.parent_id, original_parent)
        self.assertEqual(
            (
                self.assignment.location_id,
                self.assignment.position,
            ),
            original_assignment,
        )
        self.assertFalse(StorageMovement.objects.exists())

    def test_non_manager_cannot_request_preview(self):
        response = self.preview(
            self.viewer,
            self.box.pk,
            self.shelf_b.pk,
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotContains(
            response,
            "Distinct Samples:",
            status_code=403,
        )

    def test_ordinary_get_has_no_preview_result(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            response.context["storage_container_preview"],
        )
        self.assertContains(
            response, 'id="storage-container-preview"'
        )

    def test_invalid_identifier_is_handled(self):
        response = self.preview(
            self.manager,
            "invalid",
            self.shelf_b.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Select a valid container and destination.",
        )
        self.assertIsNone(
            response.context["storage_container_preview"]
        )

    def test_cannot_preview_move_to_descendant(self):
        response = self.preview(
            self.manager,
            self.shelf_a.pk,
            self.box.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "own descendant")
        self.assertIsNone(
            response.context["storage_container_preview"]
        )

    def test_room_cannot_be_moved_as_container(self):
        response = self.preview(
            self.manager,
            self.room_a.pk,
            self.shelf_b.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Rooms and individual positions",
        )

    def test_position_cannot_be_destination(self):
        response = self.preview(
            self.manager,
            self.box.pk,
            self.position.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "A position cannot be a container destination.",
        )

    def test_inactive_destination_ancestor_is_rejected(self):
        self.room_b.is_active = False
        self.room_b.save(update_fields=["is_active"])

        response = self.preview(
            self.manager,
            self.box.pk,
            self.shelf_b.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Source and destination hierarchies must be active.",
        )

        self.box.refresh_from_db()
        self.assertEqual(self.box.parent_id, self.shelf_a.pk)
        self.assertFalse(StorageMovement.objects.exists())
