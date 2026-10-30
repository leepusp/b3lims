from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from unittest.mock import patch

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageWorkspace,
)
from core.services.storage_subtree_unassign_v8149 import (
    delete_storage_subtree_unassign_v8149,
    preview_storage_subtree_unassign_v8149,
)


class StorageSubtreeUnassignV8149Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="v8149-owner"
        )
        self.outsider = User.objects.create_user(
            username="v8149-outsider"
        )
        self.workspace = StorageWorkspace.objects.create(
            name="V8149 Storage",
            owner=self.owner,
            scope="personal",
        )
        self.parent = StorageLocation.objects.create(
            name="V8149 Freezer",
            workspace=self.workspace,
            location_type="freezer",
        )
        self.box = StorageLocation.objects.create(
            name="V8149 Box",
            parent=self.parent,
            workspace=self.workspace,
            location_type="box",
        )
        self.outside = StorageLocation.objects.create(
            name="V8149 External",
            workspace=self.workspace,
            location_type="box",
        )

    def sample(self, identifier, owner=None, text=""):
        return Sample.objects.create(
            sample_id=identifier,
            sample_type="Other",
            organism_name="Test organism",
            owner=owner or self.owner,
            status="available",
            is_active=True,
            storage_location=text,
        )

    def assign(self, sample, location, rank=1, position="A1"):
        return SampleStorageAssignment.objects.create(
            sample=sample,
            location=location,
            rank=rank,
            is_primary=(rank == 1),
            position=position,
            status="active",
        )

    def preview(self, location=None):
        return preview_storage_subtree_unassign_v8149(
            actor=self.owner,
            location_id=(location or self.parent).pk,
        )

    def delete(self, preview, location=None):
        return delete_storage_subtree_unassign_v8149(
            actor=self.owner,
            location_id=(location or self.parent).pk,
            confirmation="DELETE",
            preview_token=preview["confirm_token"],
            reason="Test infrastructure cleanup",
        )

    def test_parent_deletion_unassigns_without_deleting_sample(self):
        sample = self.sample("V8149-A")
        self.assign(sample, self.box)
        preview = self.preview()
        self.assertTrue(preview["can_unassign"])
        self.assertEqual(preview["location_count"], 2)
        self.assertEqual(preview["orphaned_count"], 1)

        self.delete(preview)
        sample.refresh_from_db()

        self.assertEqual(sample.storage_location, "")
        self.assertFalse(sample.storage_assignments.exists())
        self.assertTrue(Sample.objects.filter(pk=sample.pk).exists())
        self.assertFalse(
            StorageLocation.objects.filter(pk=self.parent.pk).exists()
        )
        self.assertTrue(LogEntry.objects.exists())

    def test_secondary_location_and_position_are_preserved(self):
        sample = self.sample("V8149-B")
        self.assign(sample, self.box, rank=1, position="A1")
        kept = self.assign(
            sample, self.outside, rank=2, position="B7"
        )
        self.delete(self.preview())

        kept.refresh_from_db()
        sample.refresh_from_db()

        self.assertEqual(kept.position, "B7")
        self.assertEqual(kept.rank, 1)
        self.assertTrue(kept.is_primary)
        self.assertEqual(
            sample.storage_location,
            self.outside.full_path + " > B7",
        )

    def test_legacy_only_path_is_cleared(self):
        sample = self.sample(
            "V8149-C",
            text=self.box.full_path + " > C1",
        )
        preview = self.preview()
        self.assertEqual(preview["textual_count"], 1)

        self.delete(preview)
        sample.refresh_from_db()
        self.assertEqual(sample.storage_location, "")

    def test_history_is_preserved(self):
        sample = self.sample("V8149-D")
        self.assign(sample, self.box)
        old_path = self.box.full_path
        movement = StorageMovement.objects.create(
            movement_type="container",
            origin_location=self.box,
            origin_path=old_path,
        )
        preview = self.preview()
        self.assertTrue(preview["can_unassign"])

        self.delete(preview)
        movement.refresh_from_db()
        self.assertIsNone(movement.origin_location_id)
        self.assertEqual(movement.origin_path, old_path)

    def test_unauthorized_sample_blocks_everything(self):
        sample = self.sample(
            "V8149-E", owner=self.outsider
        )
        self.assign(sample, self.box)
        preview = self.preview()

        self.assertFalse(preview["can_unassign"])
        self.assertEqual(
            preview["unauthorized_sample_count"], 1
        )
        self.assertEqual(preview["confirm_token"], "")
        self.assertTrue(
            StorageLocation.objects.filter(pk=self.parent.pk).exists()
        )

    def test_stale_confirmation_is_rejected(self):
        sample = self.sample("V8149-F")
        assignment = self.assign(sample, self.box)
        preview = self.preview()

        SampleStorageAssignment.objects.filter(
            pk=assignment.pk
        ).update(position="A2")

        with self.assertRaises(ValidationError):
            self.delete(preview)

        self.assertTrue(
            StorageLocation.objects.filter(pk=self.parent.pk).exists()
        )

    def test_failure_rolls_back_all_records(self):
        sample = self.sample("V8149-G")
        self.assign(sample, self.box)
        self.assign(sample, self.outside, rank=2)
        preview = self.preview()

        with patch(
            "core.services.storage_subtree_unassign_v8149."
            "sync_primary_storage_legacy_for_samples",
            side_effect=RuntimeError("Injected rollback"),
        ):
            with self.assertRaises(RuntimeError):
                self.delete(preview)

        self.assertEqual(
            sample.storage_assignments.count(), 2
        )
        self.assertTrue(
            StorageLocation.objects.filter(pk=self.parent.pk).exists()
        )

    def test_confirmation_reason_and_token_are_required(self):
        preview = self.preview()

        with self.assertRaises(ValidationError):
            delete_storage_subtree_unassign_v8149(
                actor=self.owner,
                location_id=self.parent.pk,
                confirmation="DELETE",
                preview_token=preview["confirm_token"],
                reason="",
            )

        with self.assertRaises(ValidationError):
            delete_storage_subtree_unassign_v8149(
                actor=self.owner,
                location_id=self.parent.pk,
                confirmation="DELETE",
                preview_token="invalid",
                reason="Test cleanup",
            )

    def _storage_url(self):
        from django.conf import settings
        from django.urls import reverse

        url = reverse("storage_workspace")
        prefix = (settings.FORCE_SCRIPT_NAME or "").rstrip("/")

        if prefix and url.startswith(prefix + "/"):
            return url[len(prefix):]

        return url

    def test_http_confirm_occupied_parent(self):
        sample = self.sample("V8149-HTTP-A")
        self.assign(sample, self.box)
        self.client.force_login(self.owner)

        url = self._storage_url()

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="b3s-delete-dialog"')

        response = self.client.get(
            url,
            {"b3s_delete_preview": str(self.parent.pk)},
        )

        self.assertEqual(response.status_code, 200)

        preview = response.json()
        self.assertTrue(preview["can_unassign"])
        self.assertTrue(preview["confirm_token"])

        response = self.client.post(
            url,
            {
                "action": "delete_subtree_and_unassign",
                "location_id": str(self.parent.pk),
                "confirm": "DELETE",
                "preview_token": preview["confirm_token"],
                "reason": "Remove obsolete storage hierarchy",
            },
        )

        self.assertEqual(response.status_code, 302)

        sample.refresh_from_db()

        self.assertEqual(sample.storage_location, "")
        self.assertFalse(sample.storage_assignments.exists())

        self.assertFalse(
            StorageLocation.objects.filter(
                pk=self.parent.pk
            ).exists()
        )

    def test_http_outsider_cannot_preview(self):
        self.client.force_login(self.outsider)

        response = self.client.get(
            self._storage_url(),
            {"b3s_delete_preview": str(self.parent.pk)},
        )

        self.assertEqual(response.status_code, 403)

        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.parent.pk
            ).exists()
        )

    def test_http_stale_confirmation_does_not_delete(self):
        sample = self.sample("V8149-HTTP-B")
        assignment = self.assign(sample, self.box)
        self.client.force_login(self.owner)

        url = self._storage_url()

        preview = self.client.get(
            url,
            {"b3s_delete_preview": str(self.parent.pk)},
        ).json()

        SampleStorageAssignment.objects.filter(
            pk=assignment.pk
        ).update(position="D4")

        response = self.client.post(
            url,
            {
                "action": "delete_subtree_and_unassign",
                "location_id": str(self.parent.pk),
                "confirm": "DELETE",
                "preview_token": preview["confirm_token"],
                "reason": "Remove obsolete storage hierarchy",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.parent.pk
            ).exists()
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.position, "D4")

    def test_http_csrf_required_for_deletion(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)

        response = client.post(
            self._storage_url(),
            {
                "action": "delete_subtree_and_unassign",
                "location_id": str(self.parent.pk),
                "confirm": "DELETE",
                "reason": "Remove obsolete storage hierarchy",
            },
        )

        self.assertEqual(response.status_code, 403)

        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.parent.pk
            ).exists()
        )

    def test_preview_blocks_unmatched_legacy_survivor(self):
        sample = self.sample(
            "V8149-LEGACY-CONFLICT",
            text="Unrelated freezer > Unknown box",
        )

        self.assign(sample, self.box, rank=1)
        self.assign(
            sample, self.outside, rank=2, position="B7"
        )

        preview = self.preview()

        self.assertFalse(preview["can_unassign"])
        self.assertEqual(
            preview["legacy_conflict_count"], 1
        )
        self.assertEqual(preview["confirm_token"], "")

        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.parent.pk
            ).exists()
        )

    def test_matching_legacy_survivor_is_preserved(self):
        old_path = self.box.full_path + " > A1"
        surviving_path = self.outside.full_path + " > B7"

        sample = self.sample(
            "V8149-LEGACY-MATCH",
            text=old_path + "; " + surviving_path,
        )

        self.assign(
            sample, self.box, rank=1, position="A1"
        )
        survivor = self.assign(
            sample, self.outside, rank=2, position="B7"
        )

        preview = self.preview()

        self.assertTrue(preview["can_unassign"])
        self.assertEqual(
            preview["legacy_conflict_count"], 0
        )

        self.delete(preview)

        sample.refresh_from_db()
        survivor.refresh_from_db()

        self.assertEqual(
            sample.storage_location, surviving_path
        )
        self.assertEqual(survivor.position, "B7")
        self.assertTrue(survivor.is_primary)

    def test_delete_child_preserves_parent(self):
        sample = self.sample("V8149-CHILD")
        self.assign(sample, self.box)

        preview = self.preview(self.box)

        self.assertEqual(preview["location_count"], 1)

        self.delete(preview, self.box)

        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.parent.pk
            ).exists()
        )
        self.assertFalse(
            StorageLocation.objects.filter(
                pk=self.box.pk
            ).exists()
        )

        sample.refresh_from_db()
        self.assertEqual(sample.storage_location, "")
        self.assertFalse(sample.storage_assignments.exists())
