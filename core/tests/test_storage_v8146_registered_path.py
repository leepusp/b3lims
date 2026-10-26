"""V8.14.6C1 physical path registration."""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)


class RegisteredPathV8146Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(
            username="v8146c1-owner",
            is_staff=True,
        )
        cls.outsider = User.objects.create_user(
            username="v8146c1-outsider",
            is_staff=True,
        )
        cls.workspace = StorageWorkspace.objects.create(
            name="Custom hierarchy workspace",
            scope="personal",
            owner=cls.owner,
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("storage_path_register_v8146")

    def register(self, path, **extra):
        data = {
            "workspace_id": str(self.workspace.pk),
            "path": path,
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_workspace_list_exists_without_roots(self):
        self.assertFalse(StorageLocation.objects.exists())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["workspaces"][0]["id"],
            self.workspace.pk,
        )

    def test_creates_root_and_custom_children(self):
        response = self.register("teste > TESTE1 > BBAMS")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created_count"], 3)

        root = StorageLocation.objects.get(
            name="teste",
            parent__isnull=True,
            workspace=self.workspace,
        )
        child = StorageLocation.objects.get(
            name="TESTE1",
            parent=root,
        )
        terminal = StorageLocation.objects.get(
            name="BBAMS",
            parent=child,
        )

        for location in (root, child, terminal):
            self.assertEqual(location.location_type, "other")
            self.assertEqual(
                location.workspace_id, self.workspace.pk
            )

        self.assertEqual(
            response.json()["anchor"]["id"], terminal.pk
        )

    def test_reuses_existing_parent_and_preserves_type(self):
        parent = StorageLocation.objects.create(
            name="Original freezer",
            location_type="freezer",
            workspace=self.workspace,
        )

        response = self.register(
            "Original freezer > User-defined level"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created_count"], 1)

        parent.refresh_from_db()
        self.assertEqual(parent.location_type, "freezer")
        self.assertTrue(
            StorageLocation.objects.filter(
                parent=parent,
                name="User-defined level",
                location_type="other",
            ).exists()
        )

    def test_repeat_is_idempotent(self):
        first = self.register("Room A > Custom B")
        second = self.register("room a > custom b")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["created_count"], 0)
        self.assertEqual(StorageLocation.objects.count(), 2)

    def test_invalid_path_has_no_partial_writes(self):
        response = self.register(
            "Valid root > " + "X" * 151
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StorageLocation.objects.count(), 0)

    def test_foreign_workspace_denied(self):
        self.client.force_login(self.outsider)

        response = self.register("Unauthorized root")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageLocation.objects.exists())
        self.assertEqual(
            self.client.get(self.url).json()["workspaces"],
            [],
        )

    def test_inactive_parent_denied(self):
        StorageLocation.objects.create(
            name="Inactive",
            location_type="other",
            workspace=self.workspace,
            is_active=False,
        )

        response = self.register("Inactive > New")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            StorageLocation.objects.filter(name="New").exists()
        )

    def test_client_cannot_assign_a_predefined_type(self):
        response = self.register(
            "Free name",
            location_type="room",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            StorageLocation.objects.get(
                name="Free name"
            ).location_type,
            "other",
        )

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)

        response = client.post(self.url, {
            "workspace_id": str(self.workspace.pk),
            "path": "Unauthorized CSRF",
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageLocation.objects.exists())

    def test_type_selector_removed_from_shared_interface(self):
        html = (
            Path(settings.BASE_DIR) /
            "core/interfaces/internal/samples/_storage_child_v8146.html"
        ).read_text()

        js = (
            Path(settings.BASE_DIR) /
            "core/static/internal/samples/storage_child_v8146.js"
        ).read_text()

        self.assertIn('id="storageChildCreateV8146"', html)
        self.assertNotIn('id="storageChildTypeV8146"', html)
        self.assertIn('"storage_location_hidden"', js)
        self.assertIn(
            "b3:storage-child-created-v8146", js
        )
