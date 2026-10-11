"""Functional tests for the Inventory Storage workspace."""

from unittest import (
    skipIf,
    skipUnless,
)

from django.conf import settings
from django.contrib.auth import (
    get_user_model,
)
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import (
    Sample,
    SampleStorageLevel,
)
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)


STANDALONE_RUNTIME = (
    getattr(
        settings,
        "BIOBANK_RUNTIME_PROFILE",
        None,
    )
    == "standalone"
)


@skipUnless(
    STANDALONE_RUNTIME,
    "Standalone Storage workspace tests require standalone settings.",
)
class StandaloneStorageWorkspaceTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username="storage-workspace-user",
                password="test-password",
            )
        )

        self.client.force_login(
            self.user
        )

    def test_workspace_is_available(
        self,
    ):
        response = self.client.get(
            reverse(
                "storage_workspace"
            ),
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Physical Storage",
        )

        self.assertContains(
            response,
            "Add location",
        )

    def test_local_user_can_create_hierarchy(
        self,
    ):
        response = self.client.post(
            reverse(
                "storage_workspace"
            ),
            {
                "action": "create_location",
                "name": "Room 1",
                "location_type": "room",
                "rank": "1",
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        room = StorageLocation.objects.get(
            name="Room 1"
        )

        response = self.client.post(
            reverse(
                "storage_workspace"
            ),
            {
                "action": "create_location",
                "parent_id": str(
                    room.pk
                ),
                "name": "Freezer A",
                "location_type": "freezer",
                "rank": "1",
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        freezer = StorageLocation.objects.get(
            name="Freezer A"
        )

        self.assertEqual(
            freezer.parent_id,
            room.pk,
        )

        self.assertEqual(
            freezer.full_path,
            "Room 1 > Freezer A",
        )

    def test_sample_can_be_assigned_to_existing_location(
        self,
    ):
        sample = Sample.objects.create(
            sample_id="STORAGE-WORKSPACE-001",
            sample_type="Other",
            organism_name="Storage UI sample",
            owner=self.user,
        )

        room = StorageLocation.objects.create(
            name="Room 1",
            location_type="room",
        )

        freezer = StorageLocation.objects.create(
            name="Freezer A",
            parent=room,
            location_type="freezer",
        )

        response = self.client.post(
            reverse(
                "storage_workspace"
            ),
            {
                "action": "assign_sample",
                "sample_id": str(
                    sample.pk
                ),
                "location_id": str(
                    freezer.pk
                ),
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        assignment = (
            SampleStorageAssignment.objects
            .select_related(
                "location"
            )
            .get(
                sample=sample
            )
        )

        self.assertEqual(
            assignment.location_id,
            freezer.pk,
        )

        self.assertTrue(
            assignment.is_primary
        )

        sample.refresh_from_db()

        self.assertEqual(
            sample.storage_location,
            "Room 1 > Freezer A",
        )

        self.assertEqual(
            list(
                SampleStorageLevel.objects
                .filter(
                    sample=sample
                )
                .order_by(
                    "level_index"
                )
                .values_list(
                    "name",
                    flat=True,
                )
            ),
            [
                "Room 1",
                "Freezer A",
            ],
        )

    def test_occupied_location_cannot_be_deactivated(
        self,
    ):
        sample = Sample.objects.create(
            sample_id="STORAGE-WORKSPACE-002",
            sample_type="Other",
            owner=self.user,
        )

        location = StorageLocation.objects.create(
            name="Freezer Occupied",
            location_type="freezer",
        )

        SampleStorageAssignment.objects.create(
            sample=sample,
            location=location,
            rank=1,
            is_primary=True,
            status="active",
        )

        response = self.client.post(
            reverse(
                "storage_workspace"
            ),
            {
                "action": "deactivate_location",
                "location_id": str(
                    location.pk
                ),
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        location.refresh_from_db()

        self.assertTrue(
            location.is_active
        )


@skipIf(
    STANDALONE_RUNTIME,
    "Institutional policy tests require non-standalone settings.",
)
class InstitutionalStorageWorkspaceTests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="institutional-storage-user",
            password="test-password",
        )

        self.staff = User.objects.create_user(
            username="institutional-storage-staff",
            password="test-password",
            is_staff=True,
        )

    def test_non_staff_cannot_create_infrastructure(
        self,
    ):
        self.client.force_login(
            self.user
        )

        response = self.client.post(
            reverse(
                "storage_workspace"
            ),
            {
                "action": "create_location",
                "name": "Forbidden Freezer",
                "location_type": "freezer",
                "rank": "1",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertFalse(
            StorageLocation.objects
            .filter(
                name="Forbidden Freezer"
            )
            .exists()
        )

    def test_staff_can_create_infrastructure(
        self,
    ):
        self.client.force_login(
            self.staff
        )

        response = self.client.post(
            reverse(
                "storage_workspace"
            ),
            {
                "action": "create_location",
                "name": "Managed Freezer",
                "location_type": "freezer",
                "rank": "1",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            StorageLocation.objects
            .filter(
                name="Managed Freezer"
            )
            .exists()
        )
