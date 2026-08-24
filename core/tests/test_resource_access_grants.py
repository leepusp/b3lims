from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import ResearchGroup, ResourceAccessGrant
from core.services.resource_access import (
    active_resource_grants,
    grant_resource_access,
    has_explicit_resource_access,
    resource_grants_for_user,
    revoke_resource_access,
)


class ResourceAccessGrantTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="resource-owner",
            password="test-password",
        )
        self.viewer = User.objects.create_user(
            username="resource-viewer",
            password="test-password",
        )
        self.editor = User.objects.create_user(
            username="resource-editor",
            password="test-password",
        )
        self.group_coordinator = User.objects.create_user(
            username="resource-coordinator",
            password="test-password",
        )
        self.group_member = User.objects.create_user(
            username="resource-member",
            password="test-password",
        )
        self.outsider = User.objects.create_user(
            username="resource-outsider",
            password="test-password",
        )

        self.resource = ResearchGroup.objects.create(
            name="Resource target group",
            coordinator=self.owner,
        )
        self.principal_group = ResearchGroup.objects.create(
            name="Granted principal group",
            coordinator=self.group_coordinator,
        )
        self.principal_group.members.add(
            self.group_member,
        )

    def grant_user(
        self,
        user,
        level="view",
        expires_at=None,
    ):
        return grant_resource_access(
            resource=self.resource,
            access_level=level,
            granted_by=self.owner,
            user=user,
            expires_at=expires_at,
        )

    def test_user_grant_resolves_generic_resource(self):
        grant = self.grant_user(
            self.viewer,
        )

        self.assertEqual(
            grant.content_object,
            self.resource,
        )
        self.assertEqual(
            grant.user,
            self.viewer,
        )
        self.assertIsNone(
            grant.research_group,
        )
        self.assertTrue(
            grant.is_active,
        )

    def test_exactly_one_principal_is_required(self):
        grant = ResourceAccessGrant(
            content_object=self.resource,
            access_level="view",
            granted_by=self.owner,
        )

        with self.assertRaises(ValidationError):
            grant.full_clean()

        grant.user = self.viewer
        grant.research_group = self.principal_group

        with self.assertRaises(ValidationError):
            grant.full_clean()

    def test_active_user_grant_is_unique(self):
        self.grant_user(
            self.viewer,
        )

        duplicate = ResourceAccessGrant(
            content_object=self.resource,
            user=self.viewer,
            access_level="edit",
            granted_by=self.owner,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save(
                    force_insert=True,
                )

    def test_group_grant_covers_coordinator_and_member(self):
        grant_resource_access(
            resource=self.resource,
            access_level="edit",
            granted_by=self.owner,
            research_group=self.principal_group,
        )

        self.assertTrue(
            has_explicit_resource_access(
                self.group_coordinator,
                self.resource,
                "view",
            )
        )
        self.assertTrue(
            has_explicit_resource_access(
                self.group_member,
                self.resource,
                "edit",
            )
        )
        self.assertFalse(
            has_explicit_resource_access(
                self.group_member,
                self.resource,
                "manage",
            )
        )

    def test_access_hierarchy_is_monotonic(self):
        self.grant_user(
            self.editor,
            "manage",
        )

        for level in (
            "view",
            "edit",
            "manage",
        ):
            with self.subTest(level=level):
                self.assertTrue(
                    has_explicit_resource_access(
                        self.editor,
                        self.resource,
                        level,
                    )
                )

    def test_expired_grant_is_inactive(self):
        grant = self.grant_user(
            self.viewer,
            expires_at=(
                timezone.now()
                - timedelta(seconds=1)
            ),
        )

        self.assertFalse(
            grant.is_active,
        )
        self.assertFalse(
            active_resource_grants(
                self.resource,
            )
            .filter(pk=grant.pk)
            .exists()
        )
        self.assertFalse(
            has_explicit_resource_access(
                self.viewer,
                self.resource,
                "view",
            )
        )

    def test_revocation_preserves_history_and_removes_access(self):
        grant = self.grant_user(
            self.viewer,
            "edit",
        )

        revoked = revoke_resource_access(
            grant=grant,
            revoked_by=self.owner,
        )

        self.assertIsNotNone(
            revoked.revoked_at,
        )
        self.assertEqual(
            revoked.revoked_by,
            self.owner,
        )
        self.assertFalse(
            revoked.is_active,
        )
        self.assertFalse(
            has_explicit_resource_access(
                self.viewer,
                self.resource,
                "view",
            )
        )

        replacement = self.grant_user(
            self.viewer,
            "view",
        )

        self.assertNotEqual(
            replacement.pk,
            revoked.pk,
        )

    def test_grant_update_reuses_active_record(self):
        first = self.grant_user(
            self.viewer,
            "view",
        )
        second = self.grant_user(
            self.viewer,
            "edit",
        )

        self.assertEqual(
            first.pk,
            second.pk,
        )
        self.assertEqual(
            second.access_level,
            "edit",
        )

    def test_unauthenticated_and_outside_users_have_no_grant(self):
        self.grant_user(
            self.viewer,
        )

        self.assertFalse(
            has_explicit_resource_access(
                None,
                self.resource,
            )
        )
        self.assertFalse(
            resource_grants_for_user(
                self.outsider,
                self.resource,
            ).exists()
        )

    def test_unsaved_resource_is_rejected(self):
        unsaved = ResearchGroup(
            name="Unsaved resource",
            coordinator=self.owner,
        )

        with self.assertRaises(ValidationError):
            grant_resource_access(
                resource=unsaved,
                access_level="view",
                granted_by=self.owner,
                user=self.viewer,
            )
