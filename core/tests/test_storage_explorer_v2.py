from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class StorageExplorerV2Tests(TestCase):

    def test_authorized_staff_can_render_storage_explorer(self):
        user = get_user_model().objects.create_user(
            username="storage-explorer-v2-test",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("storage_workspace"), {"legacy": "1"})

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'id="storage-location-explorer"',
        )

        self.assertContains(
            response,
            'id="storage-explorer-data"',
        )
        self.assertContains(
            response,
            'id="storage-explorer-positions"',
        )
        self.assertContains(
            response,
            'id="storage-explorer-clear-position"',
        )

        self.assertContains(
            response,
            "storage_explorer_v2.js",
        )


    def test_explorer_renders_populated_storage_inventory(self):
        """Authorized inventory data feeds the read-only explorer."""
        from core.models.samples.sample import Sample
        from core.models.samples.storage import (
            SampleStorageAssignment,
            StorageLocation,
            StorageWorkspace,
        )

        user = get_user_model().objects.create_user(
            username="storage-explorer-populated",
            is_staff=True,
        )

        room = StorageLocation.objects.create(
            name="Explorer Room",
            location_type="room",
        )

        freezer = StorageLocation.objects.create(
            name="Explorer Freezer",
            location_type="freezer",
            parent=room,
        )

        workspace = StorageWorkspace.objects.create(
            name="Storage Explorer Populated Workspace",
            scope="personal",
            owner=user,
        )

        StorageLocation.objects.filter(
            pk__in=[room.pk, freezer.pk]
        ).update(workspace=workspace)

        sample = Sample.objects.create(
            sample_id="ST-EXPLORER-001",
            sample_type="Other",
            organism_name="Explorer Test Sample",
            owner=user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=freezer.full_path,
        )

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=freezer,
            rank=1,
            is_primary=True,
            position="A01",
            status="active",
        )

        self.client.force_login(user)
        response = self.client.get(reverse("storage_workspace"), {"legacy": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'data-location-id="{freezer.pk}"',
        )
        self.assertContains(
            response,
            f'data-parent-id="{room.pk}"',
        )
        self.assertContains(
            response,
            'data-assignment-sample="ST-EXPLORER-001"',
        )
        self.assertContains(
            response,
            'data-assignment-position="A01"',
        )

    def test_explorer_requires_authentication(self):
        response = self.client.get(
            reverse("storage_workspace")
        )
        self.assertEqual(response.status_code, 302)
