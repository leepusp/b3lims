from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)


class StorageRelationshipMapV89Tests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="relationship-owner",
            password="test-password",
        )

        self.other = User.objects.create_user(
            username="relationship-other",
            password="test-password",
        )

        self.own_workspace = StorageWorkspace.objects.create(
            name="Relationship Personal Workspace",
            scope="personal",
            owner=self.owner,
        )

        self.foreign_workspace = StorageWorkspace.objects.create(
            name="Relationship Foreign Workspace",
            scope="personal",
            owner=self.other,
        )

        self.own_room = StorageLocation.objects.create(
            name="Relationship Own Room",
            location_type="room",
            workspace=self.own_workspace,
            notes="",
        )

        self.foreign_room = StorageLocation.objects.create(
            name="Relationship Foreign Room",
            location_type="room",
            workspace=self.foreign_workspace,
            notes="",
        )

        self.client.force_login(self.owner)

    def test_relationship_map_loads_authorized_inventory(self):
        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'id="storage-relationship-v89"',
        )

        self.assertContains(
            response,
            "storage_relationship_v89.js",
        )

        self.assertContains(
            response,
            f'data-location-id="{self.own_room.pk}"',
        )

        self.assertContains(
            response,
            f'data-workspace-id="{self.own_workspace.pk}"',
        )

    def test_foreign_workspace_inventory_is_not_exposed(self):
        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            "Relationship Foreign Workspace",
        )

        self.assertNotContains(
            response,
            "Relationship Foreign Room",
        )
