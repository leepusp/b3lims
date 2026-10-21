from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageWorkspace,
)
from core.services.storage_subtree_delete_v8145 import (
    delete_empty_storage_subtree,
    preview_empty_storage_subtree,
)


class StorageSubtreeDeletionV8145Tests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="v8145-owner"
        )

        self.outsider = User.objects.create_user(
            username="v8145-outsider"
        )

        self.workspace = StorageWorkspace.objects.create(
            name="V8145 Isolated Storage",
            scope="personal",
            owner=self.owner,
        )

        self.root = StorageLocation.objects.create(
            name="Test Room",
            location_type="room",
            workspace=self.workspace,
        )

        self.freezer = StorageLocation.objects.create(
            name="Test Freezer",
            location_type="freezer",
            parent=self.root,
            workspace=self.workspace,
        )

        self.box = StorageLocation.objects.create(
            name="Test Box",
            location_type="box",
            parent=self.freezer,
            workspace=self.workspace,
        )

    def make_sample(self, *, text_path=""):
        return Sample.objects.create(
            sample_id="V8145-TEST-SAMPLE",
            sample_type="Other",
            organism_name="Test organism",
            owner=self.owner,
            status="available",
            is_active=True,
            storage_location=text_path,
        )

    def test_empty_subtree_preview(self):
        result = preview_empty_storage_subtree(
            actor=self.owner,
            location_id=self.root.pk,
        )

        self.assertTrue(result["can_delete"])
        self.assertEqual(result["location_count"], 3)
        self.assertEqual(result["descendant_count"], 2)
        self.assertEqual(result["assignment_count"], 0)

        self.assertEqual(
            StorageLocation.objects.count(),
            3,
        )

    def test_empty_subtree_can_be_deleted_atomically(self):
        result = delete_empty_storage_subtree(
            actor=self.owner,
            location_id=self.root.pk,
            confirmation="DELETE",
        )

        self.assertEqual(result["location_count"], 3)
        self.assertFalse(
            StorageLocation.objects.filter(
                pk__in=[
                    self.root.pk,
                    self.freezer.pk,
                    self.box.pk,
                ]
            ).exists()
        )

        self.assertTrue(
            LogEntry.objects.filter(
                user_id=self.owner.pk,
                object_id=str(self.root.pk),
            ).exists()
        )

    def test_confirmation_is_required(self):
        with self.assertRaises(ValidationError):
            delete_empty_storage_subtree(
                actor=self.owner,
                location_id=self.root.pk,
                confirmation="",
            )

        self.assertEqual(
            StorageLocation.objects.count(),
            3,
        )

    def test_outsider_cannot_preview_or_delete(self):
        with self.assertRaises(PermissionDenied):
            preview_empty_storage_subtree(
                actor=self.outsider,
                location_id=self.root.pk,
            )

        with self.assertRaises(PermissionDenied):
            delete_empty_storage_subtree(
                actor=self.outsider,
                location_id=self.root.pk,
                confirmation="DELETE",
            )

        self.assertEqual(
            StorageLocation.objects.count(),
            3,
        )

    def test_structured_sample_assignment_blocks_delete(self):
        sample = self.make_sample()

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=self.box,
            rank=1,
            is_primary=True,
            position="B5",
            status="active",
        )

        preview = preview_empty_storage_subtree(
            actor=self.owner,
            location_id=self.root.pk,
        )

        self.assertFalse(preview["can_delete"])
        self.assertEqual(preview["sample_count"], 1)
        self.assertEqual(preview["assignment_count"], 1)

        with self.assertRaises(ValidationError):
            delete_empty_storage_subtree(
                actor=self.owner,
                location_id=self.root.pk,
                confirmation="DELETE",
            )

        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.box.pk
            ).exists()
        )

    def test_historical_textual_path_blocks_delete(self):
        self.make_sample(
            text_path=self.box.full_path
        )

        preview = preview_empty_storage_subtree(
            actor=self.owner,
            location_id=self.root.pk,
        )

        self.assertGreater(
            preview["textual_count"],
            0,
        )
        self.assertFalse(preview["can_delete"])

        with self.assertRaises(ValidationError):
            delete_empty_storage_subtree(
                actor=self.owner,
                location_id=self.root.pk,
                confirmation="DELETE",
            )

    def test_movement_history_blocks_delete(self):
        StorageMovement.objects.create(
            movement_type="container",
            origin_location=self.box,
            origin_path=self.box.full_path,
        )

        preview = preview_empty_storage_subtree(
            actor=self.owner,
            location_id=self.root.pk,
        )

        self.assertFalse(preview["can_delete"])
        self.assertTrue(preview["blockers"])

        with self.assertRaises(ValidationError):
            delete_empty_storage_subtree(
                actor=self.owner,
                location_id=self.root.pk,
                confirmation="DELETE",
            )

    def test_http_preview_and_delete(self):
        self.client.force_login(self.owner)
        from django.conf import settings
        from django.urls import resolve

        external_url = reverse("storage_workspace")
        prefix = (
            settings.FORCE_SCRIPT_NAME or ""
        ).rstrip("/")

        if prefix:
            self.assertTrue(
                external_url.startswith(prefix + "/")
            )
            internal_url = external_url[len(prefix):]
        else:
            internal_url = external_url

        self.assertEqual(
            resolve(internal_url).url_name,
            "storage_workspace",
        )

        preview = self.client.get(
            internal_url,
            {"b3s_delete_preview": str(self.root.pk)},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["can_delete"])

        response = self.client.post(
            internal_url,
            {
                "action": "delete_empty_subtree",
                "location_id": str(self.root.pk),
                "confirm": "DELETE",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            StorageLocation.objects.filter(
                pk=self.root.pk
            ).exists()
        )
