"""V8.15.0 regression tests for empty personal Storage deletion."""

from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_workspace_delete_v8150 import (
    delete_empty_personal_storage_workspace_v8150,
)


class EmptyPersonalStorageDeletionV8150Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="storage_delete_owner_v8150",
            password="storage-test-password",
        )
        self.other = user_model.objects.create_user(
            username="storage_delete_other_v8150",
            password="storage-test-password",
        )

        self.workspace = StorageWorkspace.objects.create(
            name="Teste",
            scope="personal",
            owner=self.owner,
            research_group=None,
        )

    def delete_workspace(self, *, actor=None, confirmation="Teste"):
        return delete_empty_personal_storage_workspace_v8150(
            actor=actor or self.owner,
            workspace_id=self.workspace.pk,
            confirmation=confirmation,
        )

    def test_owner_deletes_empty_workspace_with_audit(self):
        workspace_pk = self.workspace.pk

        result = self.delete_workspace()

        self.assertEqual(result["workspace_id"], workspace_pk)
        self.assertFalse(
            StorageWorkspace.objects.filter(pk=workspace_pk).exists()
        )
        self.assertTrue(
            LogEntry.objects.filter(
                user_id=self.owner.pk,
                object_id=str(workspace_pk),
                action_flag=DELETION,
            ).exists()
        )

    def test_confirmation_must_match_exact_name(self):
        with self.assertRaises(ValidationError):
            self.delete_workspace(confirmation="teste")

        self.assertTrue(
            StorageWorkspace.objects.filter(
                pk=self.workspace.pk
            ).exists()
        )

    def test_other_user_cannot_delete(self):
        with self.assertRaises(PermissionDenied):
            self.delete_workspace(actor=self.other)

        self.assertTrue(
            StorageWorkspace.objects.filter(
                pk=self.workspace.pk
            ).exists()
        )

    def test_physical_location_blocks_workspace_delete(self):
        location = StorageLocation.objects.create(
            workspace=self.workspace,
            name="Freezer Teste",
            location_type="freezer",
            rank=1,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            self.delete_workspace()

        self.assertTrue(
            StorageWorkspace.objects.filter(
                pk=self.workspace.pk
            ).exists()
        )
        self.assertTrue(
            StorageLocation.objects.filter(
                pk=location.pk
            ).exists()
        )

    def test_inactive_location_also_blocks_delete(self):
        StorageLocation.objects.create(
            workspace=self.workspace,
            name="Inactive Box",
            location_type="box",
            rank=1,
            is_active=False,
        )

        with self.assertRaises(ValidationError):
            self.delete_workspace()

    def test_inactive_owner_cannot_delete(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            self.delete_workspace()

    def test_post_action_deletes_only_selected_workspace(self):
        survivor = StorageWorkspace.objects.create(
            name="Keep This Storage",
            scope="personal",
            owner=self.owner,
        )

        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("storage_workspace"),
            {
                "action": "delete_empty_personal_storage_v8150",
                "workspace_id": str(self.workspace.pk),
                "confirm_workspace_name": "Teste",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            StorageWorkspace.objects.filter(
                pk=self.workspace.pk
            ).exists()
        )
        self.assertTrue(
            StorageWorkspace.objects.filter(
                pk=survivor.pk
            ).exists()
        )

    def test_manage_has_workspace_delete_form(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="b3s-delete-storage-form-v8150"',
        )
        self.assertContains(
            response,
            'value="delete_empty_personal_storage_v8150"',
        )
