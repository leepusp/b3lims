"""V8.14.6B2: authorized creation of physical hierarchy children."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageWorkspace,
)


class StorageChildLocationHTTPV8146Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="v8146b2-owner",
            is_staff=True,
        )

        cls.outsider = User.objects.create_user(
            username="v8146b2-outsider",
            is_staff=True,
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="V8146B2 owner workspace",
            scope="personal",
            owner=cls.owner,
        )

        cls.other_workspace = StorageWorkspace.objects.create(
            name="V8146B2 outsider workspace",
            scope="personal",
            owner=cls.outsider,
        )

        cls.parent = StorageLocation.objects.create(
            name="Freezer with a user-defined name",
            location_type="freezer",
            workspace=cls.workspace,
        )

        cls.second_parent = StorageLocation.objects.create(
            name="Second parent",
            location_type="shelf",
            workspace=cls.workspace,
            parent=cls.parent,
        )

        cls.foreign_parent = StorageLocation.objects.create(
            name="Private foreign parent",
            location_type="room",
            workspace=cls.other_workspace,
        )

    def setUp(self):
        self.url = reverse(
            "storage_location_child_create_v8146"
        )
        self.client.force_login(self.owner)

    def payload(self, **changes):
        data = {
            "parent_id": str(self.parent.pk),
            "name": "BBAMS",
            "location_type": "other",
        }
        data.update(changes)
        return data

    def test_creates_child_with_exact_parent_and_workspace(self):
        response = self.client.post(
            self.url, self.payload()
        )

        self.assertEqual(response.status_code, 201)

        payload = response.json()
        self.assertTrue(payload["ok"])

        node = StorageLocation.objects.get(
            pk=payload["anchor"]["id"]
        )

        self.assertEqual(node.name, "BBAMS")
        self.assertEqual(
            node.parent_id, self.parent.pk
        )
        self.assertEqual(
            node.workspace_id, self.workspace.pk
        )
        self.assertEqual(
            node.location_type, "other"
        )
        self.assertEqual(
            payload["anchor"]["full_path"],
            node.full_path,
        )

        self.assertFalse(
            SampleStorageAssignment.objects.exists()
        )
        self.assertFalse(
            StorageMovement.objects.exists()
        )

    def test_duplicate_sibling_name_is_rejected(self):
        first = self.client.post(
            self.url, self.payload()
        )
        self.assertEqual(first.status_code, 201)

        duplicate = self.client.post(
            self.url,
            self.payload(name="bbams"),
        )

        self.assertEqual(duplicate.status_code, 400)

        self.assertEqual(
            StorageLocation.objects.filter(
                parent=self.parent,
                name__iexact="BBAMS",
            ).count(),
            1,
        )

        # The pre-existing sibling must remain untouched.
        self.assertTrue(
            StorageLocation.objects.filter(
                pk=self.second_parent.pk,
                parent=self.parent,
            ).exists()
        )

    def test_same_name_under_different_parents_is_allowed(self):
        first = self.client.post(
            self.url, self.payload()
        )

        second = self.client.post(
            self.url,
            self.payload(
                parent_id=str(self.second_parent.pk)
            ),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        first_node = StorageLocation.objects.get(
            pk=first.json()["anchor"]["id"]
        )
        second_node = StorageLocation.objects.get(
            pk=second.json()["anchor"]["id"]
        )

        self.assertNotEqual(
            first_node.parent_id,
            second_node.parent_id,
        )

    def test_unrelated_user_cannot_create_in_workspace(self):
        self.client.force_login(self.outsider)

        before = StorageLocation.objects.count()

        response = self.client.post(
            self.url, self.payload()
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            StorageLocation.objects.count(),
            before,
        )

    def test_foreign_parent_cannot_be_selected(self):
        before = StorageLocation.objects.count()

        response = self.client.post(
            self.url,
            self.payload(
                parent_id=str(self.foreign_parent.pk)
            ),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            StorageLocation.objects.count(),
            before,
        )

    def test_inactive_parent_is_rejected(self):
        self.parent.is_active = False
        self.parent.save(
            update_fields=["is_active"]
        )

        response = self.client.post(
            self.url, self.payload()
        )

        self.assertNotEqual(response.status_code, 201)

        self.assertFalse(
            StorageLocation.objects.filter(
                parent=self.parent,
                name="BBAMS",
            ).exists()
        )

    def test_invalid_parent_and_type_are_rejected(self):
        missing = self.client.post(
            self.url,
            self.payload(parent_id=""),
        )

        self.assertEqual(missing.status_code, 400)

        invalid_type = self.client.post(
            self.url,
            self.payload(location_type="unrecognized"),
        )

        self.assertEqual(invalid_type.status_code, 400)

    def test_get_cannot_create_child(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_csrf_is_required(self):
        protected_client = Client(
            enforce_csrf_checks=True
        )
        protected_client.force_login(self.owner)

        before = StorageLocation.objects.count()

        response = protected_client.post(
            self.url, self.payload()
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            StorageLocation.objects.count(),
            before,
        )
