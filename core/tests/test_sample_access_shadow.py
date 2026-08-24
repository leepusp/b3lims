from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    ResearchGroup,
    Sample,
    SampleAccessGrant,
)
from core.permissions.samples import (
    can_edit_sample,
    can_manage_sample_sharing,
    can_view_sample,
)
from core.services.resource_access import (
    grant_resource_access,
    revoke_resource_access,
)
from core.services.sample_access_shadow import (
    observe_sample_access_shadow,
)


@override_settings(
    BIOBANK_SAMPLE_GRANT_SHADOW_MODE=True,
)
class SampleAccessShadowTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="shadow-owner",
            password="test-password",
        )
        self.viewer = User.objects.create_user(
            username="shadow-viewer",
            password="test-password",
        )
        self.group_coordinator = User.objects.create_user(
            username="shadow-coordinator",
            password="test-password",
        )

        self.group = ResearchGroup.objects.create(
            name="Shadow principal group",
            coordinator=self.group_coordinator,
        )
        self.group.members.add(
            self.viewer
        )

        self.sample = Sample.objects.create(
            sample_id="SHADOW-001",
            sample_type="Other",
            organism_name="Shadow Sample",
            owner=self.owner,
            status="available",
            is_active=True,
            is_public=False,
        )

    def legacy_grant(
        self,
        level="view",
        *,
        expires_at=None,
    ):
        return SampleAccessGrant.objects.create(
            sample=self.sample,
            user=self.viewer,
            access_level=level,
            granted_by=self.owner,
            expires_at=expires_at,
        )

    def generic_user_grant(
        self,
        level="view",
        *,
        expires_at=None,
    ):
        return grant_resource_access(
            resource=self.sample,
            access_level=level,
            granted_by=self.owner,
            user=self.viewer,
            expires_at=expires_at,
        )

    @override_settings(
        BIOBANK_SAMPLE_GRANT_SHADOW_MODE=False,
    )
    def test_shadow_disabled_does_not_query_generic(self):
        with patch(
            (
                "core.services.sample_access_shadow."
                "has_explicit_resource_access"
            )
        ) as generic_access:
            self.assertFalse(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        generic_access.assert_not_called()

    def test_no_explicit_grants_match(self):
        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_not_called()

    def test_legacy_view_remains_authoritative(self):
        self.legacy_grant("view")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertTrue(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_called_once()

    def test_generic_view_does_not_authorize(self):
        self.generic_user_grant("view")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_called_once()

    def test_mirrored_view_grants_match(self):
        self.legacy_grant("view")
        self.generic_user_grant("view")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertTrue(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_not_called()

    def test_legacy_edit_remains_authoritative(self):
        self.legacy_grant("edit")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertTrue(
                can_edit_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_called_once()

    def test_generic_edit_does_not_authorize(self):
        self.generic_user_grant("edit")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_edit_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_called_once()

    def test_mirrored_edit_grants_match(self):
        self.legacy_grant("edit")
        self.generic_user_grant("edit")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertTrue(
                can_edit_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_not_called()

    def test_generic_manage_does_not_not_enable_sharing(self):
        self.generic_user_grant("manage")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_manage_sample_sharing(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_called_once()

    def test_generic_group_grant_does_not_authorize(self):
        grant_resource_access(
            resource=self.sample,
            access_level="view",
            granted_by=self.owner,
            research_group=self.group,
        )

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_called_once()

    def test_expired_generic_grant_is_ignored(self):
        self.generic_user_grant(
            "view",
            expires_at=(
                timezone.now()
                - timedelta(seconds=1)
            ),
        )

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_not_called()

    def test_revoked_generic_grant_is_ignored(self):
        grant = self.generic_user_grant(
            "view"
        )

        revoke_resource_access(
            grant=grant,
            revoked_by=self.owner,
        )

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            self.assertFalse(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        warning.assert_not_called()

    def test_evaluation_error_preserves_legacy_decision(self):
        self.legacy_grant("view")

        with patch(
            (
                "core.services.sample_access_shadow."
                "has_explicit_resource_access"
            ),
            side_effect=RuntimeError(
                "synthetic failure"
            ),
        ), patch(
            "core.services.sample_access_shadow.logger.error"
        ) as error:
            self.assertTrue(
                can_view_sample(
                    self.viewer,
                    self.sample,
                )
            )

        error.assert_called_once()

    def test_mismatch_log_excludes_resource_identities(self):
        self.generic_user_grant("view")

        with patch(
            "core.services.sample_access_shadow.logger.warning"
        ) as warning:
            observation = observe_sample_access_shadow(
                self.viewer,
                self.sample,
                required_level="view",
                legacy_allowed=False,
            )

        self.assertFalse(
            observation.equivalent
        )

        rendered = " ".join(
            str(value)
            for value in warning.call_args.args
        )

        self.assertNotIn(
            self.viewer.username,
            rendered,
        )
        self.assertNotIn(
            self.sample.sample_id,
            rendered,
        )
        self.assertNotIn(
            str(self.sample.pk),
            rendered,
        )
