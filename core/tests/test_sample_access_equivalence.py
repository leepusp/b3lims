from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import (
    ResearchGroup,
    ResourceAccessGrant,
    Sample,
    SampleAccessGrant,
)
from core.permissions.samples import (
    can_edit_sample,
    can_view_sample,
)
from core.services.resource_access import (
    grant_resource_access,
    revoke_resource_access,
)
from core.services.sample_access_equivalence import (
    evaluate_sample_access_equivalence,
)


class SampleAccessEquivalenceTests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.owner = (
            User.objects.create_user(
                username=(
                    "equivalence-owner"
                ),
                password=(
                    "test-password"
                ),
            )
        )

        self.viewer = (
            User.objects.create_user(
                username=(
                    "equivalence-viewer"
                ),
                password=(
                    "test-password"
                ),
            )
        )

        self.group_coordinator = (
            User.objects.create_user(
                username=(
                    "equivalence-coordinator"
                ),
                password=(
                    "test-password"
                ),
            )
        )

        self.group_member = (
            User.objects.create_user(
                username=(
                    "equivalence-member"
                ),
                password=(
                    "test-password"
                ),
            )
        )

        self.sample = (
            Sample.objects.create(
                sample_id=(
                    "EQUIVALENCE-001"
                ),
                sample_type="Other",
                organism_name=(
                    "Equivalence Sample"
                ),
                owner=self.owner,
                status="available",
                is_active=True,
                is_public=False,
            )
        )

        self.principal_group = (
            ResearchGroup.objects.create(
                name=(
                    "Equivalence principal group"
                ),
                coordinator=(
                    self.group_coordinator
                ),
            )
        )

        self.principal_group.members.add(
            self.group_member
        )

    def legacy_grant(
        self,
        level="view",
        *,
        user=None,
        expires_at=None,
    ):
        return (
            SampleAccessGrant.objects.create(
                sample=self.sample,
                user=(
                    user
                    or self.viewer
                ),
                access_level=level,
                granted_by=self.owner,
                expires_at=expires_at,
            )
        )

    def generic_user_grant(
        self,
        level="view",
        *,
        user=None,
        expires_at=None,
    ):
        return grant_resource_access(
            resource=self.sample,
            access_level=level,
            granted_by=self.owner,
            user=(
                user
                or self.viewer
            ),
            expires_at=expires_at,
        )

    def evaluate(
        self,
        user=None,
    ):
        return (
            evaluate_sample_access_equivalence(
                user or self.viewer,
                self.sample,
            )
        )

    def test_no_grants_are_equivalent(
        self,
    ):
        result = self.evaluate()

        self.assertIsNone(
            result.legacy_level
        )
        self.assertIsNone(
            result.generic_level
        )
        self.assertFalse(
            result.legacy_view
        )
        self.assertFalse(
            result.generic_view
        )
        self.assertTrue(
            result.behavior_equivalent
        )
        self.assertTrue(
            result.migration_equivalent
        )
        self.assertEqual(
            result.mismatch_reasons,
            (),
        )

    def test_mirrored_view_grants_are_equivalent(
        self,
    ):
        self.legacy_grant(
            "view"
        )
        self.generic_user_grant(
            "view"
        )

        result = self.evaluate()

        self.assertEqual(
            result.legacy_level,
            "view",
        )
        self.assertEqual(
            result.generic_level,
            "view",
        )
        self.assertTrue(
            result.legacy_view
        )
        self.assertFalse(
            result.legacy_edit
        )
        self.assertTrue(
            result.generic_view
        )
        self.assertFalse(
            result.generic_edit
        )
        self.assertTrue(
            result.migration_equivalent
        )

    def test_mirrored_edit_grants_are_equivalent(
        self,
    ):
        self.legacy_grant(
            "edit"
        )
        self.generic_user_grant(
            "edit"
        )

        result = self.evaluate()

        self.assertTrue(
            result.legacy_view
        )
        self.assertTrue(
            result.legacy_edit
        )
        self.assertTrue(
            result.generic_view
        )
        self.assertTrue(
            result.generic_edit
        )
        self.assertFalse(
            result.generic_manage
        )
        self.assertTrue(
            result.migration_equivalent
        )

    def test_legacy_only_grant_reports_behavior_mismatch(
        self,
    ):
        self.legacy_grant(
            "view"
        )

        result = self.evaluate()

        self.assertFalse(
            result.behavior_equivalent
        )
        self.assertFalse(
            result.migration_equivalent
        )
        self.assertIn(
            "view_behavior_mismatch",
            result.mismatch_reasons,
        )

    def test_generic_only_grant_reports_behavior_mismatch(
        self,
    ):
        self.generic_user_grant(
            "edit"
        )

        result = self.evaluate()

        self.assertFalse(
            result.behavior_equivalent
        )
        self.assertFalse(
            result.migration_equivalent
        )
        self.assertIn(
            "view_behavior_mismatch",
            result.mismatch_reasons,
        )
        self.assertIn(
            "edit_behavior_mismatch",
            result.mismatch_reasons,
        )

    def test_equally_expired_grants_are_equivalent(
        self,
    ):
        expired = (
            timezone.now()
            - timedelta(
                seconds=1
            )
        )

        self.legacy_grant(
            "edit",
            expires_at=expired,
        )
        self.generic_user_grant(
            "edit",
            expires_at=expired,
        )

        result = self.evaluate()

        self.assertIsNone(
            result.legacy_level
        )
        self.assertIsNone(
            result.generic_level
        )
        self.assertTrue(
            result.migration_equivalent
        )

    def test_revoked_generic_grant_does_not_match_active_legacy(
        self,
    ):
        self.legacy_grant(
            "view"
        )

        generic_grant = (
            self.generic_user_grant(
                "view"
            )
        )

        revoke_resource_access(
            grant=generic_grant,
            revoked_by=self.owner,
        )

        result = self.evaluate()

        self.assertEqual(
            result.legacy_level,
            "view",
        )
        self.assertIsNone(
            result.generic_level
        )
        self.assertFalse(
            result.migration_equivalent
        )

    def test_manage_level_is_not_legacy_migration_equivalent(
        self,
    ):
        self.legacy_grant(
            "edit"
        )

        self.generic_user_grant(
            ResourceAccessGrant
            .AccessLevel
            .MANAGE
        )

        result = self.evaluate()

        self.assertTrue(
            result.behavior_equivalent
        )
        self.assertTrue(
            result.generic_manage
        )
        self.assertFalse(
            result.migration_equivalent
        )
        self.assertIn(
            "generic_manage_not_representable",
            result.mismatch_reasons,
        )

    def test_group_principal_is_detected_as_nonrepresentable(
        self,
    ):
        grant_resource_access(
            resource=self.sample,
            access_level="view",
            granted_by=self.owner,
            research_group=(
                self.principal_group
            ),
        )

        result = self.evaluate(
            self.group_member
        )

        self.assertTrue(
            result.generic_view
        )
        self.assertTrue(
            result.applicable_group_grant
        )
        self.assertFalse(
            result.migration_equivalent
        )
        self.assertIn(
            (
                "generic_group_principal_"
                "not_representable"
            ),
            result.mismatch_reasons,
        )

    def test_owner_policy_is_outside_explicit_equivalence(
        self,
    ):
        result = self.evaluate(
            self.owner
        )

        self.assertTrue(
            can_view_sample(
                self.owner,
                self.sample,
            )
        )
        self.assertTrue(
            can_edit_sample(
                self.owner,
                self.sample,
            )
        )
        self.assertFalse(
            result.legacy_view
        )
        self.assertFalse(
            result.generic_view
        )
        self.assertTrue(
            result.migration_equivalent
        )

    def test_generic_grant_does_not_change_active_sample_policy(
        self,
    ):
        self.generic_user_grant(
            "edit"
        )

        self.assertFalse(
            can_view_sample(
                self.viewer,
                self.sample,
            )
        )
        self.assertFalse(
            can_edit_sample(
                self.viewer,
                self.sample,
            )
        )

        result = self.evaluate()

        self.assertTrue(
            result.generic_edit
        )
        self.assertFalse(
            result.migration_equivalent
        )

    def test_mirrored_grants_preserve_current_legacy_policy(
        self,
    ):
        self.legacy_grant(
            "edit"
        )
        self.generic_user_grant(
            "edit"
        )

        self.assertTrue(
            can_view_sample(
                self.viewer,
                self.sample,
            )
        )
        self.assertTrue(
            can_edit_sample(
                self.viewer,
                self.sample,
            )
        )
        self.assertTrue(
            self.evaluate()
            .migration_equivalent
        )
