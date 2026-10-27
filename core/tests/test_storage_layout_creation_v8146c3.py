"""HTTP regression tests for storage layout creation."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageLocationLayoutV8146C3,
    StorageWorkspace,
)


class StorageLayoutCreationC3Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="storage-c3b-owner",
        )
        cls.other = User.objects.create_user(
            username="storage-c3b-other",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="C3B owner workspace",
            scope="personal",
            owner=cls.owner,
        )

        cls.foreign_workspace = StorageWorkspace.objects.create(
            name="C3B other workspace",
            scope="personal",
            owner=cls.other,
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse(
            "storage_location_create_with_layout_v8146c3"
        )

    def data(self, **changes):
        values = {
            "action": "create_location",
            "workspace_id": str(self.workspace.pk),
            "parent_id": "",
            "name": "Caixa C3B",
            "location_type": "other",
            "rank": "1",
            "notes": "",
            "organization": "grid",
            "rows": "9",
            "columns": "9",
            "type_label": "Caixa criogênica",
            "temperature_label": "-80 C",
        }
        values.update(changes)
        return values

    def test_create_grid_and_persist_capacity(self):
        response = self.client.post(
            self.url,
            self.data(),
        )

        self.assertEqual(response.status_code, 302)

        location = StorageLocation.objects.get(
            workspace=self.workspace,
            name="Caixa C3B",
        )

        layout = StorageLocationLayoutV8146C3.objects.get(
            location=location
        )

        self.assertEqual(layout.organization, "grid")
        self.assertEqual(layout.rows, 9)
        self.assertEqual(layout.columns, 9)
        self.assertEqual(layout.capacity, 81)
        self.assertEqual(
            layout.type_label,
            "Caixa criogênica",
        )
        self.assertEqual(
            SampleStorageAssignment.objects.filter(
                location=location
            ).count(),
            0,
        )

    def test_create_free_organization(self):
        response = self.client.post(
            self.url,
            self.data(
                organization="free",
                rows="",
                columns="",
            ),
        )

        self.assertEqual(response.status_code, 302)

        location = StorageLocation.objects.get(
            workspace=self.workspace,
            name="Caixa C3B",
        )

        self.assertIsNone(
            location.layout_v8146c3.capacity
        )

    def test_invalid_dimensions_create_nothing(self):
        response = self.client.post(
            self.url,
            self.data(rows="27"),
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            StorageLocation.objects.filter(
                name="Caixa C3B"
            ).exists()
        )

    def test_foreign_workspace_is_denied(self):
        response = self.client.post(
            self.url,
            self.data(
                workspace_id=str(
                    self.foreign_workspace.pk
                )
            ),
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            StorageLocation.objects.filter(
                name="Caixa C3B"
            ).exists()
        )

    def test_foreign_parent_is_denied(self):
        foreign_parent = StorageLocation.objects.create(
            name="Foreign parent C3B",
            location_type="other",
            workspace=self.foreign_workspace,
        )

        response = self.client.post(
            self.url,
            self.data(
                parent_id=str(foreign_parent.pk)
            ),
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            StorageLocation.objects.filter(
                name="Caixa C3B"
            ).exists()
        )

    def test_anonymous_request_cannot_create(self):
        self.client.logout()

        response = self.client.post(
            self.url,
            self.data(),
        )

        self.assertNotEqual(response.status_code, 200)

        self.assertFalse(
            StorageLocation.objects.filter(
                name="Caixa C3B"
            ).exists()
        )

    def test_invalid_organization_is_rejected(self):
        response = self.client.post(
            self.url,
            self.data(organization="unknown"),
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            StorageLocation.objects.filter(
                name="Caixa C3B"
            ).exists()
        )

    def test_existing_location_can_be_parent(self):
        parent = StorageLocation.objects.create(
            name="Rack C3B",
            workspace=self.workspace,
            location_type="other",
        )

        response = self.client.post(
            self.url,
            self.data(parent_id=str(parent.pk)),
        )

        self.assertEqual(response.status_code, 302)

        created = StorageLocation.objects.get(
            workspace=self.workspace,
            name="Caixa C3B",
        )

        self.assertEqual(created.parent_id, parent.pk)
        self.assertEqual(
            created.layout_v8146c3.capacity,
            81,
        )
