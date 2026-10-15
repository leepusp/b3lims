from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)


class StorageVisibilityIsolationV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="visibility-v8-owner",
        )
        cls.viewer = User.objects.create_user(
            username="visibility-v8-viewer",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="Visibility V8 Private Workspace",
            scope="personal",
            owner=cls.owner,
        )

        cls.freezer = StorageLocation.objects.create(
            name="Visibility V8 Private Freezer",
            location_type="freezer",
            workspace=cls.workspace,
        )

        cls.box = StorageLocation.objects.create(
            name="Visibility V8 Private Box",
            location_type="box",
            parent=cls.freezer,
            workspace=cls.workspace,
        )

        def create_assignment(identifier, owner, public, pos):
            sample = Sample.objects.create(
                sample_id=identifier,
                sample_type="Other",
                organism_name="Visibility Test",
                owner=owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=public,
                is_embargoed=False,
            )

            SampleStorageAssignment.objects.create(
                sample=sample,
                location=cls.box,
                position=pos,
                rank=1,
                is_primary=True,
                status="active",
            )

        create_assignment(
            "VISIBILITY-PUBLIC-V8",
            cls.owner,
            True,
            "A01",
        )

        create_assignment(
            "VISIBILITY-FOREIGN-LOCATION-V8",
            cls.viewer,
            False,
            "A02",
        )

    def test_public_sample_does_not_expose_physical_storage(self):
        self.client.force_login(self.viewer)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            "VISIBILITY-PUBLIC-V8",
        )
        self.assertNotContains(
            response,
            "Visibility V8 Private Freezer",
        )
        self.assertNotContains(
            response,
            'data-assignment-position="A01"',
        )

    def test_own_sample_in_foreign_workspace_stays_hidden(self):
        self.client.force_login(self.viewer)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            "VISIBILITY-FOREIGN-LOCATION-V8",
        )
        self.assertNotContains(
            response,
            'data-assignment-position="A02"',
        )

        self.assertEqual(
            response.context["storage_assignment_total"],
            0,
        )

    def test_owner_can_view_authorized_sample_and_location(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "VISIBILITY-PUBLIC-V8",
        )
        self.assertContains(
            response,
            "Visibility V8 Private Box",
        )

        self.assertEqual(
            response.context["storage_assignment_total"],
            1,
        )
