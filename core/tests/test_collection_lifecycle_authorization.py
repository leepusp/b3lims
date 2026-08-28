from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    ResearchGroup,
    ResourceAccessGrant,
)
from core.permissions.collections import (
    can_delete_collection,
    can_edit_collection,
)
from core.services.collection_sharing import (
    grant_collection_access,
)


User = get_user_model()


class CollectionLifecycleAuthorizationTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-lifecycle-owner",
        )

        cls.coordinator = User.objects.create_user(
            username="collection-lifecycle-coordinator",
        )

        cls.member = User.objects.create_user(
            username="collection-lifecycle-member",
        )

        cls.unrelated = User.objects.create_user(
            username="collection-lifecycle-unrelated",
        )

        cls.group = ResearchGroup.objects.create(
            name="Collection Lifecycle Group",
            coordinator=cls.coordinator,
        )

        cls.group.members.add(
            cls.member
        )

    def collection(
        self,
        name,
        *,
        owner=None,
        research_group=None,
    ):
        return Collection.objects.create(
            name=name,
            description="Lifecycle authorization test",
            owner=owner or self.owner,
            research_group=research_group,
            is_public=False,
            is_active=True,
        )

    def list_url(
        self,
    ):
        return reverse(
            "collections_list"
        )

    def deactivate(
        self,
        collection,
    ):
        return self.client.post(
            self.list_url(),
            {
                "action":
                    "deactivate_collection",
                "collection_id":
                    str(
                        collection.pk
                    ),
            },
        )

    def assert_active(
        self,
        collection,
    ):
        collection.refresh_from_db()

        self.assertTrue(
            collection.is_active
        )

    def assert_deactivated(
        self,
        collection,
    ):
        collection.refresh_from_db()

        self.assertFalse(
            collection.is_active
        )

    def test_owner_can_see_and_execute_deactivation(self):
        collection = self.collection(
            "Owner Lifecycle Collection"
        )

        self.client.force_login(
            self.owner
        )

        self.assertTrue(
            can_delete_collection(
                self.owner,
                collection,
            )
        )

        listing = self.client.get(
            self.list_url()
        )

        self.assertEqual(
            listing.status_code,
            200,
        )

        self.assertContains(
            listing,
            "Deactivate",
        )

        response = self.deactivate(
            collection
        )

        self.assertRedirects(
            response,
            self.list_url(),
        )

        self.assert_deactivated(
            collection
        )

    def test_superuser_can_see_and_execute_deactivation(self):
        admin = User.objects.create_superuser(
            username="collection-lifecycle-admin",
            email="admin@example.org",
            password="test-password",
        )

        collection = self.collection(
            "Admin Lifecycle Collection"
        )

        self.client.force_login(
            admin
        )

        self.assertTrue(
            can_delete_collection(
                admin,
                collection,
            )
        )

        listing = self.client.get(
            self.list_url()
        )

        self.assertContains(
            listing,
            "Deactivate",
        )

        response = self.deactivate(
            collection
        )

        self.assertRedirects(
            response,
            self.list_url(),
        )

        self.assert_deactivated(
            collection
        )

    def test_research_group_coordinator_can_deactivate(self):
        collection = self.collection(
            "Coordinator Lifecycle Collection",
            research_group=self.group,
        )

        self.client.force_login(
            self.coordinator
        )

        self.assertTrue(
            can_delete_collection(
                self.coordinator,
                collection,
            )
        )

        listing = self.client.get(
            self.list_url()
        )

        self.assertContains(
            listing,
            "Deactivate",
        )

        response = self.deactivate(
            collection
        )

        self.assertRedirects(
            response,
            self.list_url(),
        )

        self.assert_deactivated(
            collection
        )

    def test_ordinary_group_member_keeps_edit_but_cannot_deactivate(self):
        collection = self.collection(
            "Member Lifecycle Collection",
            research_group=self.group,
        )

        self.client.force_login(
            self.member
        )

        self.assertTrue(
            can_edit_collection(
                self.member,
                collection,
            )
        )

        self.assertFalse(
            can_delete_collection(
                self.member,
                collection,
            )
        )

        listing = self.client.get(
            self.list_url()
        )

        self.assertContains(
            listing,
            collection.name,
        )

        self.assertNotContains(
            listing,
            "Deactivate",
        )

        self.assertContains(
            listing,
            "No lifecycle actions",
        )

        response = self.deactivate(
            collection
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assert_active(
            collection
        )

    def test_explicit_view_edit_and_manage_grants_do_not_grant_deactivation(
        self,
    ):
        cases = (
            (
                "view",
                ResourceAccessGrant
                .AccessLevel
                .VIEW,
                False,
            ),
            (
                "edit",
                ResourceAccessGrant
                .AccessLevel
                .EDIT,
                True,
            ),
            (
                "manage",
                ResourceAccessGrant
                .AccessLevel
                .MANAGE,
                True,
            ),
        )

        for (
            suffix,
            access_level,
            expected_edit,
        ) in cases:
            with self.subTest(
                access_level=access_level
            ):
                user = User.objects.create_user(
                    username=(
                        "collection-lifecycle-"
                        f"{suffix}"
                    ),
                )

                collection = self.collection(
                    (
                        "Explicit "
                        f"{suffix.title()} "
                        "Lifecycle Collection"
                    )
                )

                grant_collection_access(
                    collection=collection,
                    access_level=access_level,
                    granted_by=self.owner,
                    user=user,
                )

                self.assertEqual(
                    can_edit_collection(
                        user,
                        collection,
                    ),
                    expected_edit,
                )

                self.assertFalse(
                    can_delete_collection(
                        user,
                        collection,
                    )
                )

                self.client.force_login(
                    user
                )

                listing = self.client.get(
                    self.list_url()
                )

                self.assertContains(
                    listing,
                    collection.name,
                )

                self.assertNotContains(
                    listing,
                    "Deactivate",
                )

                self.assertContains(
                    listing,
                    "No lifecycle actions",
                )

                response = (
                    self.deactivate(
                        collection
                    )
                )

                self.assertEqual(
                    response.status_code,
                    403,
                )

                self.assert_active(
                    collection
                )

    def test_unrelated_user_cannot_directly_deactivate_private_collection(
        self,
    ):
        collection = self.collection(
            "Unrelated Lifecycle Collection"
        )

        self.client.force_login(
            self.unrelated
        )

        self.assertFalse(
            can_delete_collection(
                self.unrelated,
                collection,
            )
        )

        listing = self.client.get(
            self.list_url()
        )

        self.assertNotContains(
            listing,
            collection.name,
        )

        response = self.deactivate(
            collection
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assert_active(
            collection
        )
