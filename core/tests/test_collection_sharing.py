from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Collection,
    ResearchGroup,
    ResourceAccessGrant,
    Sample,
)
from core.permissions.collections import (
    can_edit_collection,
    can_manage_collection_permissions,
    can_view_collection,
)
from core.permissions.samples import (
    visible_samples_for_user,
)
from core.services.collection_sharing import (
    active_collection_access_grants,
    grant_collection_access,
)


class CollectionSharingTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-share-owner",
            password="test-password",
        )

        cls.coordinator = User.objects.create_user(
            username="collection-share-coordinator",
            password="test-password",
        )

        cls.member = User.objects.create_user(
            username="collection-share-member",
            password="test-password",
        )

        cls.outsider = User.objects.create_user(
            username="collection-share-outsider",
            password="test-password",
        )

        cls.delegate_target = User.objects.create_user(
            username="collection-share-target",
            password="test-password",
        )

        cls.group = ResearchGroup.objects.create(
            name="Collection Sharing Group",
            coordinator=cls.coordinator,
        )

        cls.group.members.add(
            cls.member
        )

        cls.external_group = ResearchGroup.objects.create(
            name="External Sharing Group",
            coordinator=cls.outsider,
        )

        cls.external_group.members.add(
            cls.delegate_target
        )

        cls.collection = Collection.objects.create(
            name="Sharing Test Collection",
            description="Collection sharing regression fixture.",
            owner=cls.owner,
            research_group=cls.group,
            is_active=True,
            is_public=False,
        )

        cls.other_collection = Collection.objects.create(
            name="Other Sharing Collection",
            owner=cls.owner,
            is_active=True,
            is_public=False,
        )

        cls.private_sample = Sample.objects.create(
            sample_id="COL-SHARE-PRIVATE",
            sample_type="Bacteria",
            owner=cls.owner,
            is_active=True,
            is_public=False,
        )

        cls.private_sample.collections.add(
            cls.collection
        )

    def detail_url(self):
        return reverse(
            "collection_detail",
            args=[
                self.collection.pk,
            ],
        )

    def share_url(self):
        return reverse(
            "collection_share",
            args=[
                self.collection.pk,
            ],
        )

    def revoke_url(
        self,
        grant,
    ):
        return reverse(
            "collection_share_revoke",
            args=[
                self.collection.pk,
                grant.pk,
            ],
        )

    def test_owner_sees_collection_sharing_ui(self):
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
            "Collection Access",
        )
        self.assertContains(
            response,
            "Share Collection",
        )
        self.assertContains(
            response,
            "collection-share-outsider",
        )
        self.assertContains(
            response,
            "External Sharing Group",
        )
        self.assertContains(
            response,
            "Manage permits access delegation",
        )

    def test_ordinary_group_member_cannot_manage_collection_sharing(self):
        self.assertFalse(
            can_manage_collection_permissions(
                self.member,
                self.collection,
            )
        )

        self.client.force_login(
            self.member
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertNotContains(
            response,
            "Share Collection",
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"user:{self.outsider.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW,
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_owner_can_share_collection_with_user_without_sample_leak(self):
        self.assertFalse(
            self.outsider.research_groups.filter(
                pk=self.group.pk
            ).exists()
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"user:{self.outsider.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW,
                # These fields must never control the resource target.
                "content_type": "sample",
                "object_id": str(
                    self.private_sample.pk
                ),
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(),
        )

        grants = (
            active_collection_access_grants(
                self.collection
            )
        )

        self.assertEqual(
            grants.count(),
            1,
        )

        grant = grants.get()

        expected_content_type = (
            ContentType.objects
            .get_for_model(
                Collection,
                for_concrete_model=False,
            )
        )

        self.assertEqual(
            grant.content_type_id,
            expected_content_type.pk,
        )
        self.assertEqual(
            grant.object_id,
            str(
                self.collection.pk
            ),
        )
        self.assertEqual(
            grant.user,
            self.outsider,
        )
        self.assertEqual(
            grant.access_level,
            ResourceAccessGrant
            .AccessLevel
            .VIEW,
        )

        self.assertTrue(
            can_view_collection(
                self.outsider,
                self.collection,
            )
        )

        self.assertFalse(
            visible_samples_for_user(
                self.outsider
            )
            .filter(
                pk=self.private_sample.pk
            )
            .exists()
        )

        self.assertFalse(
            self.outsider.research_groups.filter(
                pk=self.group.pk
            ).exists()
        )

    def test_owner_can_share_collection_with_research_group(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"group:{self.external_group.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .EDIT,
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(),
        )

        grant = (
            active_collection_access_grants(
                self.collection
            )
            .get()
        )

        self.assertEqual(
            grant.research_group,
            self.external_group,
        )

        self.assertTrue(
            can_edit_collection(
                self.delegate_target,
                self.collection,
            )
        )

        self.assertFalse(
            self.delegate_target
            .research_groups
            .filter(
                pk=self.group.pk
            )
            .exists()
        )

    def test_explicit_manage_grantee_can_delegate_but_not_delete_contract_changes(self):
        grant_collection_access(
            collection=self.collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .MANAGE
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.assertTrue(
            can_manage_collection_permissions(
                self.outsider,
                self.collection,
            )
        )

        self.client.force_login(
            self.outsider
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"user:{self.delegate_target.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW,
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(),
        )

        self.assertTrue(
            can_view_collection(
                self.delegate_target,
                self.collection,
            )
        )

    def test_future_expiration_is_persisted(self):
        self.client.force_login(
            self.owner
        )

        expires_at = (
            timezone.now()
            + timedelta(
                days=7
            )
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"user:{self.outsider.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW,
                "expires_at":
                    timezone.localtime(
                        expires_at
                    ).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ),
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(),
        )

        grant = (
            active_collection_access_grants(
                self.collection
            )
            .get()
        )

        self.assertIsNotNone(
            grant.expires_at
        )
        self.assertGreater(
            grant.expires_at,
            timezone.now(),
        )

    def test_past_expiration_is_rejected(self):
        self.client.force_login(
            self.owner
        )

        expires_at = (
            timezone.now()
            - timedelta(
                hours=1
            )
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"user:{self.outsider.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW,
                "expires_at":
                    timezone.localtime(
                        expires_at
                    ).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ),
            },
            follow=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Access expiration must be in the future.",
        )

        self.assertFalse(
            active_collection_access_grants(
                self.collection
            ).exists()
        )

    def test_revoke_preserves_grant_audit_history(self):
        grant = grant_collection_access(
            collection=self.collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.revoke_url(
                grant
            )
        )

        self.assertRedirects(
            response,
            self.detail_url(),
        )

        grant.refresh_from_db()

        self.assertIsNotNone(
            grant.revoked_at
        )
        self.assertEqual(
            grant.revoked_by,
            self.owner,
        )

        self.assertFalse(
            active_collection_access_grants(
                self.collection
            )
            .filter(
                pk=grant.pk
            )
            .exists()
        )

        self.assertTrue(
            ResourceAccessGrant.objects.filter(
                pk=grant.pk
            ).exists()
        )

        self.assertFalse(
            can_view_collection(
                self.outsider,
                self.collection,
            )
        )

    def test_grant_for_other_collection_cannot_be_revoked_through_this_collection(self):
        other_grant = grant_collection_access(
            collection=self.other_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            reverse(
                "collection_share_revoke",
                args=[
                    self.collection.pk,
                    other_grant.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        other_grant.refresh_from_db()

        self.assertIsNone(
            other_grant.revoked_at
        )

    def test_owner_cannot_receive_redundant_explicit_grant(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.share_url(),
            {
                "principal":
                    f"user:{self.owner.pk}",
                "access_level":
                    ResourceAccessGrant
                    .AccessLevel
                    .MANAGE,
            },
            follow=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Collection owner already has full access.",
        )

        self.assertFalse(
            active_collection_access_grants(
                self.collection
            ).filter(
                user=self.owner
            ).exists()
        )
