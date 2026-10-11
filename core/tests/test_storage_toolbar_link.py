from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class StorageToolbarLinkTests(TestCase):

    def test_sample_inventory_has_storage_link(self):
        user = get_user_model().objects.create_user(
            username="storage-toolbar-test",
            is_staff=True,
        )

        self.client.force_login(user)

        response = self.client.get(
            reverse("samples_list")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'href="%s"' % reverse("storage_workspace"),
        )

    def test_storage_workspace_opens_for_staff(self):
        user = get_user_model().objects.create_user(
            username="storage-workspace-navigation",
            is_staff=True,
        )

        self.client.force_login(user)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
