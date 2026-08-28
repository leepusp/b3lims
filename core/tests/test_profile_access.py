from datetime import timedelta

from django.contrib.auth import get_user_model
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
from core.services.collection_sharing import (
    grant_collection_access,
    revoke_collection_access,
)
from core.services.resource_access import (
    grant_resource_access,
)


User = get_user_model()


class ProfileAccessTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="profile-access-user",
        )

        cls.owner = User.objects.create_user(
            username="profile-access-owner",
        )

        cls.other_user = User.objects.create_user(
            username="profile-access-other",
        )

        cls.recipient = User.objects.create_user(
            username="profile-access-recipient",
        )

    def setUp(self):
        self.client.force_login(
            self.user
        )

    def collection(
        self,
        name,
        *,
        owner=None,
        research_group=None,
        is_active=True,
    ):
        return Collection.objects.create(
            name=name,
            owner=(
                owner
                or self.owner
            ),
            research_group=research_group,
            is_active=is_active,
            is_public=False,
        )

    def profile_response(self):
        return self.client.get(
            reverse(
                "user_profile"
            )
        )

    def test_direct_collection_grant_appears_in_access_received(self):
        collection = self.collection(
            "Direct Access Collection"
        )

        grant_collection_access(
            collection=collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.user,
        )

        response = self.profile_response()

        self.assertEqual(
            response.status_code,
            200,
        )

        entries = response.context[
            "profile_access_received"
        ]

        self.assertEqual(
            len(entries),
            1,
        )

        self.assertEqual(
            entries[0][
                "collection"
            ],
            collection,
        )

        self.assertEqual(
            entries[0][
                "access_level"
            ],
            ResourceAccessGrant
            .AccessLevel
            .VIEW,
        )

        self.assertEqual(
            entries[0][
                "source_type"
            ],
            "Direct",
        )

        self.assertEqual(
            entries[0][
                "source_label"
            ],
            "Direct grant",
        )

        self.assertContains(
            response,
            "Access Received",
        )

        self.assertContains(
            response,
            "Direct Access Collection",
        )

    def test_research_group_member_and_coordinator_receive_group_grants(self):
        member_group = (
            ResearchGroup.objects.create(
                name="Profile Access Member Group",
                coordinator=self.owner,
            )
        )

        member_group.members.add(
            self.user
        )

        coordinator_group = (
            ResearchGroup.objects.create(
                name="Profile Access Coordinator Group",
                coordinator=self.user,
            )
        )

        member_collection = self.collection(
            "Member Group Access Collection"
        )

        coordinator_collection = self.collection(
            "Coordinator Group Access Collection"
        )

        grant_collection_access(
            collection=member_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .EDIT
            ),
            granted_by=self.owner,
            research_group=member_group,
        )

        grant_collection_access(
            collection=coordinator_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            research_group=coordinator_group,
        )

        response = self.profile_response()

        entries = response.context[
            "profile_access_received"
        ]

        sources = {
            entry[
                "collection"
            ].name:
                entry[
                    "source_label"
                ]
            for entry
            in entries
        }

        self.assertEqual(
            sources,
            {
                "Coordinator Group Access Collection":
                    "Profile Access Coordinator Group",
                "Member Group Access Collection":
                    "Profile Access Member Group",
            },
        )

        self.assertTrue(
            all(
                entry[
                    "source_type"
                ]
                == "Research Group"
                for entry
                in entries
            )
        )

    def test_expired_revoked_and_inactive_collection_grants_are_hidden(self):
        expired_collection = self.collection(
            "Expired Profile Collection"
        )

        revoked_collection = self.collection(
            "Revoked Profile Collection"
        )

        inactive_collection = self.collection(
            "Inactive Profile Collection"
        )

        grant_resource_access(
            resource=expired_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.user,
            expires_at=(
                timezone.now()
                - timedelta(
                    hours=1
                )
            ),
        )

        revoked_grant = (
            grant_collection_access(
                collection=revoked_collection,
                access_level=(
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW
                ),
                granted_by=self.owner,
                user=self.user,
            )
        )

        revoke_collection_access(
            collection=revoked_collection,
            grant=revoked_grant,
            revoked_by=self.owner,
        )

        grant_collection_access(
            collection=inactive_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.user,
        )

        inactive_collection.is_active = False
        inactive_collection.save(
            update_fields=(
                "is_active",
            )
        )

        response = self.profile_response()

        entries = response.context[
            "profile_access_received"
        ]

        self.assertEqual(
            entries,
            [],
        )

    def test_non_collection_and_malformed_generic_grants_are_not_exposed(self):
        sample = Sample.objects.create(
            sample_id="PROFILE-ACCESS-SAMPLE",
            sample_type="Bacteria",
            owner=self.owner,
            is_active=True,
            is_public=False,
        )

        grant_resource_access(
            resource=sample,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.user,
        )

        collection_content_type = (
            ContentType.objects
            .get_for_model(
                Collection,
                for_concrete_model=False,
            )
        )

        ResourceAccessGrant.objects.create(
            content_type=collection_content_type,
            object_id="not-a-collection-id",
            user=self.user,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
        )

        response = self.profile_response()

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.context[
                "profile_access_received"
            ],
            [],
        )

        self.assertNotContains(
            response,
            "PROFILE-ACCESS-SAMPLE",
        )

    def test_managed_access_uses_collection_permission_policy(self):
        owner_collection = self.collection(
            "Owned Managed Collection",
            owner=self.user,
        )

        coordinator_group = (
            ResearchGroup.objects.create(
                name="Managed Coordinator Group",
                coordinator=self.user,
            )
        )

        coordinator_collection = self.collection(
            "Coordinator Managed Collection",
            research_group=coordinator_group,
        )

        manage_collection = self.collection(
            "Explicit Manage Collection"
        )

        grant_collection_access(
            collection=manage_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .MANAGE
            ),
            granted_by=self.owner,
            user=self.user,
        )

        member_group = (
            ResearchGroup.objects.create(
                name="Ordinary Member Group",
                coordinator=self.owner,
            )
        )

        member_group.members.add(
            self.user
        )

        self.collection(
            "Ordinary Member Collection",
            research_group=member_group,
        )

        edit_collection = self.collection(
            "Edit Only Collection"
        )

        grant_collection_access(
            collection=edit_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .EDIT
            ),
            granted_by=self.owner,
            user=self.user,
        )

        grantor_only_collection = (
            self.collection(
                "Historical Grantor Collection"
            )
        )

        grant_resource_access(
            resource=grantor_only_collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.user,
            user=self.recipient,
        )

        response = self.profile_response()

        managed = response.context[
            "profile_access_managed"
        ]

        names = {
            entry[
                "collection"
            ].name
            for entry
            in managed
        }

        self.assertEqual(
            names,
            {
                owner_collection.name,
                coordinator_collection.name,
                manage_collection.name,
            },
        )

        self.assertNotIn(
            "Ordinary Member Collection",
            names,
        )

        self.assertNotIn(
            edit_collection.name,
            names,
        )

        self.assertNotIn(
            grantor_only_collection.name,
            names,
        )

    def test_managed_collection_active_grant_count_excludes_revoked_grants(self):
        collection = self.collection(
            "Grant Count Collection",
            owner=self.user,
        )

        active_direct = (
            grant_collection_access(
                collection=collection,
                access_level=(
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW
                ),
                granted_by=self.user,
                user=self.recipient,
            )
        )

        group = ResearchGroup.objects.create(
            name="Grant Count Group",
            coordinator=self.owner,
        )

        grant_collection_access(
            collection=collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .EDIT
            ),
            granted_by=self.user,
            research_group=group,
        )

        revoked = (
            grant_collection_access(
                collection=collection,
                access_level=(
                    ResourceAccessGrant
                    .AccessLevel
                    .VIEW
                ),
                granted_by=self.user,
                user=self.other_user,
            )
        )

        revoke_collection_access(
            collection=collection,
            grant=revoked,
            revoked_by=self.user,
        )

        response = self.profile_response()

        managed = response.context[
            "profile_access_managed"
        ]

        self.assertEqual(
            len(managed),
            1,
        )

        self.assertEqual(
            managed[0][
                "collection"
            ],
            collection,
        )

        self.assertEqual(
            managed[0][
                "active_grant_count"
            ],
            2,
        )

        self.assertIsNotNone(
            active_direct.pk
        )

    def test_superuser_manages_all_active_collections_only(self):
        admin = User.objects.create_superuser(
            username="profile-access-admin",
            email="admin@example.org",
            password="test-password",
        )

        active = self.collection(
            "Admin Active Collection"
        )

        inactive = self.collection(
            "Admin Inactive Collection",
            is_active=False,
        )

        self.client.force_login(
            admin
        )

        response = self.profile_response()

        names = {
            entry[
                "collection"
            ].name
            for entry
            in response.context[
                "profile_access_managed"
            ]
        }

        self.assertIn(
            active.name,
            names,
        )

        self.assertNotIn(
            inactive.name,
            names,
        )

    def test_profile_access_ui_is_navigation_only(self):
        received = self.collection(
            "Navigation Received Collection"
        )

        managed = self.collection(
            "Navigation Managed Collection",
            owner=self.user,
        )

        grant_collection_access(
            collection=received,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.user,
        )

        response = self.profile_response()

        self.assertContains(
            response,
            "Access Received",
        )

        self.assertContains(
            response,
            "Access Managed by You",
        )

        self.assertContains(
            response,
            reverse(
                "collection_detail",
                args=[
                    received.pk,
                ],
            ),
        )

        self.assertContains(
            response,
            reverse(
                "collection_detail",
                args=[
                    managed.pk,
                ],
            )
            + "#collection-sharing-panel",
        )

        self.assertContains(
            response,
            "Manage Access",
        )

        self.assertNotContains(
            response,
            'name="content_type"',
        )

        self.assertNotContains(
            response,
            'name="object_id"',
        )
