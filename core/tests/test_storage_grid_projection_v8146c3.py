"""Authorized Storage grid data projection regression tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageLocationLayoutV8146C3,
    StorageWorkspace,
)


class StorageGridProjectionC3Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="c3c-grid-owner",
        )
        cls.other = User.objects.create_user(
            username="c3c-grid-other",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="C3C visible workspace",
            scope="personal",
            owner=cls.owner,
        )

        cls.foreign_workspace = StorageWorkspace.objects.create(
            name="C3C foreign workspace",
            scope="personal",
            owner=cls.other,
        )

        cls.location = StorageLocation.objects.create(
            name="C3C Test Box",
            workspace=cls.workspace,
            location_type="other",
        )

        cls.foreign_location = StorageLocation.objects.create(
            name="C3C Foreign Box",
            workspace=cls.foreign_workspace,
            location_type="other",
        )

        StorageLocationLayoutV8146C3.objects.create(
            location=cls.location,
            organization="grid",
            rows=9,
            columns=9,
            type_label="Cryogenic box",
        )

    def test_authorized_grid_metadata_is_rendered(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'data-c3-organization="grid"',
        )

        self.assertContains(
            response,
            'data-c3-rows="9"',
        )

        self.assertContains(
            response,
            'data-c3-columns="9"',
        )

        self.assertContains(
            response,
            'storage_position_grid_v8146c3.js',
        )

    def test_foreign_location_is_not_exposed(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            "C3C Foreign Box",
        )
