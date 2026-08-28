from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.test import (
    RequestFactory,
    TestCase,
)
from django.urls import reverse

from core.models import (
    Collection,
    CollectionLifecycleEvent,
    ResearchGroup,
)
from core.services.collection_lifecycle import (
    deactivate_collection,
)


User = get_user_model()


class CollectionLifecycleAuditTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-audit-owner",
        )

        cls.coordinator = User.objects.create_user(
            username="collection-audit-coordinator",
        )

        cls.member = User.objects.create_user(
            username="collection-audit-member",
        )

        cls.group = ResearchGroup.objects.create(
            name="Collection Audit Group",
            coordinator=cls.coordinator,
        )

        cls.group.members.add(
            cls.member
        )

    def collection(
        self,
        name="Audited Collection",
        *,
        research_group=None,
    ):
        return Collection.objects.create(
            name=name,
            description="Lifecycle audit test",
            owner=self.owner,
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

    def test_view_deactivation_appends_actor_audit_event(self):
        collection = self.collection()

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
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

        self.assertRedirects(
            response,
            self.list_url(),
        )

        collection.refresh_from_db()

        self.assertFalse(
            collection.is_active
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

        event = events[0]

        self.assertEqual(
            event.event_type,
            CollectionLifecycleEvent
            .EventType
            .DEACTIVATED,
        )

        self.assertEqual(
            event.actor,
            self.owner,
        )

        self.assertIsNotNone(
            event.created_at
        )

        self.assertEqual(
            event.notes,
            "Collection deactivated.",
        )

    def test_coordinator_deactivation_records_coordinator_actor(self):
        collection = self.collection(
            "Coordinator Audited Collection",
            research_group=self.group,
        )

        result = deactivate_collection(
            collection=collection,
            actor=self.coordinator,
        )

        self.assertFalse(
            result.is_active
        )

        event = (
            CollectionLifecycleEvent
            .objects
            .get(
                collection=collection,
            )
        )

        self.assertEqual(
            event.actor,
            self.coordinator,
        )

        self.assertEqual(
            event.event_type,
            CollectionLifecycleEvent
            .EventType
            .DEACTIVATED,
        )

    def test_unauthorized_actor_cannot_mutate_state_or_audit(self):
        collection = self.collection(
            "Member Audited Collection",
            research_group=self.group,
        )

        with self.assertRaises(
            PermissionDenied
        ):
            deactivate_collection(
                collection=collection,
                actor=self.member,
            )

        collection.refresh_from_db()

        self.assertTrue(
            collection.is_active
        )

        self.assertFalse(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
            .exists()
        )

    def test_repeated_deactivation_is_idempotent_without_duplicate_event(
        self,
    ):
        collection = self.collection(
            "Idempotent Audited Collection"
        )

        first = deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        second = deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        self.assertFalse(
            first.is_active
        )

        self.assertFalse(
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
                    .DEACTIVATED
                ),
            )
            .count(),
            1,
        )

    def test_state_and_audit_event_are_atomic(self):
        collection = self.collection(
            "Atomic Audited Collection"
        )

        with patch(
            (
                "core.services."
                "collection_lifecycle."
                "CollectionLifecycleEvent."
                "objects.create"
            ),
            side_effect=RuntimeError(
                "Synthetic audit write failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                deactivate_collection(
                    collection=collection,
                    actor=self.owner,
                )

        collection.refresh_from_db()

        self.assertTrue(
            collection.is_active
        )

        self.assertEqual(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection=collection,
            )
            .count(),
            0,
        )

    def test_audited_collection_is_protected_from_hard_delete(self):
        collection = self.collection(
            "Protected Audited Collection"
        )

        deactivate_collection(
            collection=collection,
            actor=self.owner,
        )

        with self.assertRaises(
            ProtectedError
        ):
            collection.delete()

        self.assertTrue(
            Collection.objects
            .filter(
                pk=collection.pk,
            )
            .exists()
        )

        self.assertEqual(
            CollectionLifecycleEvent
            .objects
            .filter(
                collection_id=collection.pk,
            )
            .count(),
            1,
        )

    def test_collection_admin_blocks_lifecycle_mutation_and_delete(
        self,
    ):
        model_admin = (
            admin.site
            ._registry[
                Collection
            ]
        )

        superuser = (
            User.objects
            .create_superuser(
                username="collection-audit-admin",
                email="admin@example.org",
                password="test-password",
            )
        )

        request = (
            RequestFactory()
            .get(
                "/admin/core/collection/"
            )
        )

        request.user = superuser

        form_class = (
            model_admin
            .get_form(
                request
            )
        )

        self.assertNotIn(
            "is_active",
            form_class.base_fields,
        )

        self.assertIn(
            "is_active",
            model_admin.readonly_fields,
        )

        self.assertFalse(
            model_admin
            .has_delete_permission(
                request
            )
        )

        self.assertFalse(
            Collection
            ._meta
            .get_field(
                "is_active"
            )
            .editable
        )

    def test_lifecycle_event_admin_is_append_only(self):
        collection = self.collection(
            "Admin Event Audited Collection"
        )

        event = (
            deactivate_collection(
                collection=collection,
                actor=self.owner,
            )
            .lifecycle_events
            .get()
        )

        model_admin = (
            admin.site
            ._registry[
                CollectionLifecycleEvent
            ]
        )

        superuser = (
            User.objects
            .create_superuser(
                username="collection-event-admin",
                email="event-admin@example.org",
                password="test-password",
            )
        )

        request = (
            RequestFactory()
            .get(
                (
                    "/admin/core/"
                    "collectionlifecycleevent/"
                )
            )
        )

        request.user = superuser

        self.assertFalse(
            model_admin
            .has_add_permission(
                request
            )
        )

        self.assertFalse(
            model_admin
            .has_change_permission(
                request,
                event,
            )
        )

        self.assertFalse(
            model_admin
            .has_delete_permission(
                request,
                event,
            )
        )

        self.assertEqual(
            set(
                model_admin
                .readonly_fields
            ),
            {
                "collection",
                "event_type",
                "actor",
                "created_at",
                "notes",
            },
        )
