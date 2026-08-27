from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    ResourceAccessGrant,
    Sample,
)
from core.services.resource_access import (
    grant_resource_access,
)


class CollectionExplorerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-owner",
            password="test-password",
        )

        cls.outsider = User.objects.create_user(
            username="collection-outsider",
            password="test-password",
        )

        cls.collection = Collection.objects.create(
            name="Interactive Collection",
            description="Collection Explorer test dataset.",
            owner=cls.owner,
            is_active=True,
            is_public=False,
        )

        cls.private_sample = Sample.objects.create(
            sample_id="COL-PRIVATE-001",
            sample_type="Bacteria",
            organism_name="Private organism",
            owner=cls.owner,
            is_public=False,
            is_active=True,
        )
        cls.private_sample.collections.add(
            cls.collection
        )

        cls.public_sample = Sample.objects.create(
            sample_id="COL-PUBLIC-001",
            sample_type="Phage",
            organism_name="Public organism",
            owner=cls.owner,
            is_public=True,
            is_active=True,
        )
        cls.public_sample.collections.add(
            cls.collection
        )

        cls.inactive_sample = Sample.objects.create(
            sample_id="COL-INACTIVE-001",
            sample_type="Bacteria",
            organism_name="Inactive organism",
            owner=cls.owner,
            is_public=True,
            is_active=False,
        )
        cls.inactive_sample.collections.add(
            cls.collection
        )

    def detail_url(self):
        return reverse(
            "collection_detail",
            args=[
                self.collection.pk,
            ],
        )

    def test_owner_can_open_collection_explorer(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "Collection Explorer",
        )
        self.assertContains(
            response,
            "COL-PRIVATE-001",
        )
        self.assertContains(
            response,
            "COL-PUBLIC-001",
        )
        self.assertNotContains(
            response,
            "COL-INACTIVE-001",
        )

    def test_unauthorized_user_cannot_open_private_collection(self):
        self.client.force_login(
            self.outsider
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_collection_view_grant_does_not_leak_private_sample(self):
        grant_resource_access(
            resource=self.collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.client.force_login(
            self.outsider
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        # Collection-level sharing permits the Explorer itself.
        self.assertContains(
            response,
            "Interactive Collection",
        )

        # Public Sample remains independently visible.
        self.assertContains(
            response,
            "COL-PUBLIC-001",
        )

        # Collection access must not silently grant access to a
        # private Sample owned by another principal.
        self.assertNotContains(
            response,
            "COL-PRIVATE-001",
        )

    def test_inactive_collection_is_not_available_in_explorer(self):
        self.collection.is_active = False
        self.collection.save(
            update_fields=[
                "is_active",
            ]
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_collection_list_links_to_explorer(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            reverse(
                "collections_list"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            self.detail_url(),
        )
