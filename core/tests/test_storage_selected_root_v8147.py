from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)


class SelectedStorageRootHTTPTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="c4e_storage_owner",
            password="c4e-test-password",
        )
        self.url = reverse("storage_workspace")

    def test_new_personal_storage_is_selected_even_when_empty(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            self.url,
            {
                "action": "create_storage_workspace_v8",
                "workspace_name": "C4E Empty Storage",
                "workspace_scope": "personal",
                "research_group_id": "",
                "b3s_select_created_storage": "1",
            },
        )

        storage = StorageWorkspace.objects.get(
            owner=self.owner,
            name="C4E Empty Storage",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{self.url}?storage={storage.pk}",
        )

        self.assertFalse(
            StorageLocation.objects.filter(
                workspace=storage
            ).exists()
        )

        response = self.client.get(
            response["Location"]
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'data-b3s-storage-root="{storage.pk}"',
        )
        self.assertContains(
            response,
            f'value="{storage.pk}" selected',
        )
        self.assertEqual(
            response.context[
                "b3s_selected_storage_pk_v8147"
            ],
            storage.pk,
        )

    def test_foreign_storage_cannot_be_selected(self):
        storage = StorageWorkspace.objects.create(
            name="C4E Private Storage",
            scope="personal",
            owner=self.owner,
        )

        user_model = get_user_model()
        outsider = user_model.objects.create_user(
            username="c4e_storage_outsider",
            password="c4e-test-password",
        )

        self.client.force_login(outsider)

        response = self.client.get(
            f"{self.url}?storage={storage.pk}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            f'data-b3s-storage-root="{storage.pk}"',
        )
        self.assertIsNone(
            response.context[
                "b3s_selected_storage_pk_v8147"
            ]
        )
