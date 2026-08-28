from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    CollectionLifecycleEvent,
    ResearchGroup,
    ResourceAccessGrant,
)
from core.permissions.collections import (
    visible_collections_for_user,
)
from core.services.collection_lifecycle import (
    deactivate_collection,
    reactivate_collection,
)
from core.services.collection_sharing import (
    grant_collection_access,
)


User = get_user_model()


class CollectionRecoveryTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-recovery-owner",
        )

        cls.coordinator = User.objects.create_user(
            username="collection-recovery-coordinator",
        )

        cls.member = User.objects.create_user(
            username="collection-recovery-member",
        )

        cls.unrelated = User.objects.create_user(
            username="collection-recovery-unrelated",
        )

        cls.group = ResearchGroup.objects.create(
            name="Collection Recovery Group",
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
            description="Collection recovery test",
            owner=owner or self.owner,
            research_group=research_group,
            is_public=False,
            is_active=True,
        )

    def archive_url(
        self,
    ):
        return reverse(
            "collection_archive"
        )

    def reactivate_url(
        self,
        collection,
    ):
        return reverse(
            "collection_reactivate",
            args=[
                collection.pk,
            ],
        )

    def assert_active(
        self,
        collection,
    ):
        collection.refresh_from_db()

        self.assertTrue(
            collection.is_active
        )

    def assert_inactive(
        self,
        collection,
    ):
        collection.refresh_from_db()

        self.assertFalse(
            collection.is_active
        )

    def test_owner_sees_archived_collection_with_deactivation_provenance(
        self,
    ):
        collection = self.collection(
            "Owner Archived Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.archive_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        archived = list(
            response.context[
                "archived_collections"
            ]
        )

        self.assertEqual(
            [
                item.pk
                for item in archived
            ],
            [
                collection.pk,
            ],
        )

        event = (
            archived[0]
            .latest_deactivation_event
        )

        self.assertIsNotNone(
            event
        )

        self.assertEqual(
            event.actor,
            self.owner,
        )

        self.assertEqual(
            event.event_type,
            CollectionLifecycleEvent
            .EventType
            .DEACTIVATED,
        )

        self.assertContains(
            response,
            "Owner Archived Collection",
        )

        self.assertContains(
            response,
            "Reactivate",
        )

    def test_owner_can_reactivate_and_append_reactivated_event(
        self,
    ):
        collection = self.collection(
            "Owner Recovery Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.reactivate_url(
                collection
            )
        )

        self.assertRedirects(
            response,
            self.archive_url(),
        )

        self.assert_active(
            collection
        )

        events = list(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
            .order_by(
                "created_at",
                "pk",
            )
        )

        self.assertEqual(
            [
                event.event_type
                for event in events
            ],
            [
                CollectionLifecycleEvent
                .EventType
                .DEACTIVATED,
                CollectionLifecycleEvent
                .EventType
                .REACTIVATED,
            ],
        )

        self.assertEqual(
            events[-1].actor,
            self.owner,
        )

        self.assertEqual(
            events[-1].notes,
            "Collection reactivated.",
        )

        listing = self.client.get(
            reverse(
                "collections_list"
            )
        )

        self.assertContains(
            listing,
            "Owner Recovery Collection",
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertNotContains(
            archive,
            "Owner Recovery Collection",
        )

    def test_superuser_can_see_and_reactivate_archived_collection(
        self,
    ):
        admin = User.objects.create_superuser(
            username="collection-recovery-admin",
            email="recovery-admin@example.org",
            password="test-password",
        )

        collection = self.collection(
            "Admin Recovery Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            admin
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertContains(
            archive,
            "Admin Recovery Collection",
        )

        response = self.client.post(
            self.reactivate_url(
                collection
            )
        )

        self.assertRedirects(
            response,
            self.archive_url(),
        )

        self.assert_active(
            collection
        )

        event = (
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
                event_type=(
                    CollectionLifecycleEvent
                    .EventType
                    .REACTIVATED
                ),
            )
            .get()
        )

        self.assertEqual(
            event.actor,
            admin,
        )

    def test_research_group_coordinator_can_see_and_reactivate(
        self,
    ):
        collection = self.collection(
            "Coordinator Recovery Collection",
            research_group=self.group,
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            self.coordinator
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertContains(
            archive,
            "Coordinator Recovery Collection",
        )

        response = self.client.post(
            self.reactivate_url(
                collection
            )
        )

        self.assertRedirects(
            response,
            self.archive_url(),
        )

        self.assert_active(
            collection
        )

        event = (
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
                event_type=(
                    CollectionLifecycleEvent
                    .EventType
                    .REACTIVATED
                ),
            )
            .get()
        )

        self.assertEqual(
            event.actor,
            self.coordinator,
        )

    def test_ordinary_group_member_cannot_see_or_reactivate(
        self,
    ):
        collection = self.collection(
            "Member Hidden Archived Collection",
            research_group=self.group,
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            self.member
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertNotContains(
            archive,
            "Member Hidden Archived Collection",
        )

        response = self.client.post(
            self.reactivate_url(
                collection
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assert_inactive(
            collection
        )

        self.assertEqual(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
            .count(),
            1,
        )

    def test_explicit_view_edit_and_manage_grants_do_not_allow_reactivation(
        self,
    ):
        levels = (
            ResourceAccessGrant
            .AccessLevel
            .VIEW,
            ResourceAccessGrant
            .AccessLevel
            .EDIT,
            ResourceAccessGrant
            .AccessLevel
            .MANAGE,
        )

        for index, level in enumerate(
            levels,
            start=1,
        ):
            with self.subTest(
                access_level=level
            ):
                principal = (
                    User.objects
                    .create_user(
                        username=(
                            "collection-recovery-explicit-"
                            f"{index}"
                        ),
                    )
                )

                collection = self.collection(
                    (
                        "Explicit Recovery "
                        f"{index}"
                    )
                )

                grant_collection_access(
                    collection=collection,
                    access_level=level,
                    granted_by=self.owner,
                    user=principal,
                )

                deactivate_collection(
                    collection=collection,
                    actor=self.owner,
                )

                self.client.force_login(
                    principal
                )

                archive = self.client.get(
                    self.archive_url()
                )

                self.assertNotContains(
                    archive,
                    (
                        "Explicit Recovery "
                        f"{index}"
                    ),
                )

                response = self.client.post(
                    self.reactivate_url(
                        collection
                    )
                )

                self.assertEqual(
                    response.status_code,
                    403,
                )

                self.assert_inactive(
                    collection
                )

                self.assertEqual(
                    CollectionLifecycleEvent
                    .objects
                    .filter(
                        collection=collection,
                    )
                    .count(),
                    1,
                )

    def test_unrelated_user_cannot_see_or_reactivate(
        self,
    ):
        collection = self.collection(
            "Unrelated Hidden Archived Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            self.unrelated
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertNotContains(
            archive,
            "Unrelated Hidden Archived Collection",
        )

        response = self.client.post(
            self.reactivate_url(
                collection
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assert_inactive(
            collection
        )

        self.assertEqual(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
            .count(),
            1,
        )

    def test_reactivation_is_idempotent_without_duplicate_event(
        self,
    ):
        collection = self.collection(
            "Idempotent Recovery Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        first = reactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        second = reactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.assertTrue(
            first.is_active
        )

        self.assertTrue(
            second.is_active
        )

        self.assertEqual(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
                event_type=(
                    CollectionLifecycleEvent
                    .EventType
                    .REACTIVATED
                ),
            )
            .count(),
            1,
        )

    def test_reactivation_state_and_audit_are_atomic(
        self,
    ):
        collection = self.collection(
            "Atomic Recovery Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        with patch(
            (
                "core.services."
                "collection_lifecycle."
                "CollectionLifecycleEvent."
                "objects.create"
            ),
            side_effect=RuntimeError(
                "Synthetic reactivation audit failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                reactivate_collection(
                    collection=collection,
                    actor=self.owner,
                )

        self.assert_inactive(
            collection
        )

        events = list(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
        )

        self.assertEqual(
            len(events),
            1,
        )

        self.assertEqual(
            events[0].event_type,
            CollectionLifecycleEvent
            .EventType
            .DEACTIVATED,
        )

    def test_archive_is_separate_from_normal_active_visibility(
        self,
    ):
        active = self.collection(
            "Active Visibility Collection"
        )

        archived = self.collection(
            "Archived Visibility Collection"
        )

        deactivate_collection(
            collection=archived,
            actor=self.owner,
        )

        self.client.force_login(
            self.owner
        )

        listing = self.client.get(
            reverse(
                "collections_list"
            )
        )

        self.assertContains(
            listing,
            "Active Visibility Collection",
        )

        self.assertNotContains(
            listing,
            "Archived Visibility Collection",
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertContains(
            archive,
            "Archived Visibility Collection",
        )

        self.assertNotContains(
            archive,
            "Active Visibility Collection",
        )

        visible_ids = set(
            visible_collections_for_user(
                self.owner
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertIn(
            active.pk,
            visible_ids,
        )

        self.assertNotIn(
            archived.pk,
            visible_ids,
        )

    def test_legacy_inactive_collection_without_audit_can_be_reactivated(
        self,
    ):
        collection = self.collection(
            "Legacy Inactive Collection"
        )

        Collection.objects.filter(
            pk=collection.pk,
        ).update(
            is_active=False,
        )

        self.client.force_login(
            self.owner
        )

        archive = self.client.get(
            self.archive_url()
        )

        self.assertContains(
            archive,
            "Legacy Inactive Collection",
        )

        archived = list(
            archive.context[
                "archived_collections"
            ]
        )

        self.assertEqual(
            len(archived),
            1,
        )

        self.assertIsNone(
            archived[0]
            .latest_deactivation_event
        )

        self.assertContains(
            archive,
            "Unknown",
        )

        response = self.client.post(
            self.reactivate_url(
                collection
            )
        )

        self.assertRedirects(
            response,
            self.archive_url(),
        )

        self.assert_active(
            collection
        )

        events = list(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
        )

        self.assertEqual(
            len(events),
            1,
        )

        self.assertEqual(
            events[0].event_type,
            CollectionLifecycleEvent
            .EventType
            .REACTIVATED,
        )

        self.assertEqual(
            events[0].actor,
            self.owner,
        )

    def test_reactivate_route_requires_post(
        self,
    ):
        collection = self.collection(
            "POST Only Recovery Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.reactivate_url(
                collection
            )
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        self.assert_inactive(
            collection
        )

        self.assertEqual(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
            .count(),
            1,
        )
