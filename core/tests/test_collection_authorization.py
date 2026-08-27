from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import (
    NoReverseMatch,
    reverse,
)

from core.models import (
    Collection,
    ResearchGroup,
    ResourceAccessGrant,
)
from core.permissions.collections import (
    can_delete_collection,
    can_edit_collection,
    can_manage_collection_permissions,
    can_view_collection,
    visible_collections_for_user,
)
from core.services.resource_access import (
    grant_resource_access,
)


class CollectionAuthorizationTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-owner",
        )

        cls.coordinator = User.objects.create_user(
            username="collection-coordinator",
        )

        cls.member = User.objects.create_user(
            username="collection-member",
        )

        cls.outsider = User.objects.create_user(
            username="collection-outsider",
        )

        cls.staff = User.objects.create_user(
            username="collection-staff",
            is_staff=True,
        )

        cls.superuser = (
            User.objects.create_superuser(
                username="collection-superuser",
                email="admin@example.invalid",
                password="unused",
            )
        )

        cls.group = ResearchGroup.objects.create(
            name="Collection authorization group",
            coordinator=cls.coordinator,
        )

        cls.group.members.add(
            cls.member
        )

        cls.private = Collection.objects.create(
            name="Private authorization collection",
            owner=cls.owner,
            research_group=cls.group,
            is_public=False,
            is_active=True,
        )

        cls.active_public = (
            Collection.objects.create(
                name="Active public authorization collection",
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.inactive_public = (
            Collection.objects.create(
                name="Inactive public authorization collection",
                owner=cls.owner,
                is_public=True,
                is_active=False,
            )
        )

    def test_owner_retains_full_collection_authority(
        self,
    ):
        self.assertTrue(
            can_view_collection(
                self.owner,
                self.private,
            )
        )
        self.assertTrue(
            can_edit_collection(
                self.owner,
                self.private,
            )
        )
        self.assertTrue(
            can_manage_collection_permissions(
                self.owner,
                self.private,
            )
        )
        self.assertTrue(
            can_delete_collection(
                self.owner,
                self.private,
            )
        )

    def test_group_coordinator_retains_manage_and_delete(
        self,
    ):
        self.assertTrue(
            can_view_collection(
                self.coordinator,
                self.private,
            )
        )
        self.assertTrue(
            can_edit_collection(
                self.coordinator,
                self.private,
            )
        )
        self.assertTrue(
            can_manage_collection_permissions(
                self.coordinator,
                self.private,
            )
        )
        self.assertTrue(
            can_delete_collection(
                self.coordinator,
                self.private,
            )
        )

    def test_group_member_keeps_edit_without_manage_or_delete(
        self,
    ):
        self.assertTrue(
            can_view_collection(
                self.member,
                self.private,
            )
        )
        self.assertTrue(
            can_edit_collection(
                self.member,
                self.private,
            )
        )
        self.assertFalse(
            can_manage_collection_permissions(
                self.member,
                self.private,
            )
        )
        self.assertFalse(
            can_delete_collection(
                self.member,
                self.private,
            )
        )

    def test_outsider_has_no_implicit_private_access(
        self,
    ):
        self.assertFalse(
            can_view_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_edit_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_manage_collection_permissions(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_delete_collection(
                self.outsider,
                self.private,
            )
        )

    def test_staff_and_superuser_authority_is_preserved(
        self,
    ):
        for user in (
            self.staff,
            self.superuser,
        ):
            with self.subTest(
                username=user.username
            ):
                self.assertTrue(
                    can_view_collection(
                        user,
                        self.private,
                    )
                )
                self.assertTrue(
                    can_edit_collection(
                        user,
                        self.private,
                    )
                )
                self.assertTrue(
                    can_manage_collection_permissions(
                        user,
                        self.private,
                    )
                )
                self.assertTrue(
                    can_delete_collection(
                        user,
                        self.private,
                    )
                )

    def test_explicit_view_grant_adds_view_only(
        self,
    ):
        grant_resource_access(
            resource=self.private,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.assertTrue(
            can_view_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_edit_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_manage_collection_permissions(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_delete_collection(
                self.outsider,
                self.private,
            )
        )

    def test_explicit_edit_grant_adds_view_and_edit(
        self,
    ):
        grant_resource_access(
            resource=self.private,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .EDIT
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.assertTrue(
            can_view_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertTrue(
            can_edit_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_manage_collection_permissions(
                self.outsider,
                self.private,
            )
        )
        self.assertFalse(
            can_delete_collection(
                self.outsider,
                self.private,
            )
        )

    def test_explicit_manage_grant_adds_manage_but_not_delete(
        self,
    ):
        grant_resource_access(
            resource=self.private,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .MANAGE
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.assertTrue(
            can_view_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertTrue(
            can_edit_collection(
                self.outsider,
                self.private,
            )
        )
        self.assertTrue(
            can_manage_collection_permissions(
                self.outsider,
                self.private,
            )
        )

        # Explicit sharing authority does not grant a
        # destructive Collection lifecycle capability.
        self.assertFalse(
            can_delete_collection(
                self.outsider,
                self.private,
            )
        )

    def test_active_public_collection_remains_anonymous(
        self,
    ):
        list_response = self.client.get(
            reverse(
                "public_collections"
            )
        )

        detail_response = self.client.get(
            reverse(
                "public_collection_detail",
                args=[
                    self.active_public.pk
                ],
            )
        )

        self.assertEqual(
            list_response.status_code,
            200,
        )
        self.assertEqual(
            detail_response.status_code,
            200,
        )

        self.assertIn(
            self.active_public,
            list(
                list_response.context[
                    "collections"
                ]
            ),
        )

    def test_inactive_public_collection_is_not_listed(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_collections"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertNotIn(
            self.inactive_public,
            list(
                response.context[
                    "collections"
                ]
            ),
        )

    def test_inactive_public_collection_detail_is_not_found(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_collection_detail",
                args=[
                    self.inactive_public.pk
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_legacy_collection_acl_is_not_resurrected(
        self,
    ):
        try:
            legacy_model = apps.get_model(
                "core",
                "CollectionUserRole",
            )
        except LookupError:
            legacy_model = None

        self.assertIsNone(
            legacy_model
        )

        for name in (
            "collection_members",
            "collection_membership",
            "manage_collection_members",
            "collection_permissions",
        ):
            with self.subTest(
                route_name=name
            ):
                with self.assertRaises(
                    NoReverseMatch
                ):
                    reverse(
                        name,
                        args=[
                            self.private.pk
                        ],
                    )

    def test_visible_collections_include_explicit_grant(
        self,
    ):
        grant_resource_access(
            resource=self.private,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        visible_ids = set(
            visible_collections_for_user(
                self.outsider
            ).values_list(
                "pk",
                flat=True,
            )
        )

        self.assertIn(
            self.private.pk,
            visible_ids,
        )

        self.assertNotIn(
            self.inactive_public.pk,
            visible_ids,
        )
