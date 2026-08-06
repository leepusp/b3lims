from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.middleware.pam_remote_user import (
    PamIdentity,
    _synchronize_pam_groups,
)


@override_settings(
    BIOBANK_PAM_GROUP_PREFIX="pam:",
    BIOBANK_PAM_EXCLUDED_GROUPS=(
        "wheel",
        "dbadmin",
        "unrestricted",
        "max90",
        "vglusers",
        "cryosparc",
        "biobank",
    ),
)
class PamGroupSynchronizationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ccalomeno",
        )
        self.identity = PamIdentity(
            username="ccalomeno",
            uid=1075,
            gid=1002,
            home=Path("/home/ccalomeno"),
            shell="/bin/bash",
        )

        self.manual_group = Group.objects.create(
            name="BBAMS"
        )
        self.stale_group = Group.objects.create(
            name="pam:oldlab"
        )
        self.user.groups.add(
            self.manual_group,
            self.stale_group,
        )

    @staticmethod
    def group_record(name):
        return SimpleNamespace(
            gr_name=name
        )

    @patch(
        "core.middleware.pam_remote_user."
        "grp.getgrgid"
    )
    @patch(
        "core.middleware.pam_remote_user."
        "os.getgrouplist"
    )
    def test_sync_preserves_manual_and_filters_operational_groups(
        self,
        mocked_getgrouplist,
        mocked_getgrgid,
    ):
        mocked_getgrouplist.return_value = [
            1002,
            1074,
            1075,
            1076,
            1200,
        ]

        names = {
            1002: "leepbioinfo",
            1074: "max90",
            1075: "ccalomeno",
            1076: "biobank",
            1200: "collaboration",
        }

        mocked_getgrgid.side_effect = (
            lambda group_id: self.group_record(
                names[group_id]
            )
        )

        _synchronize_pam_groups(
            self.user,
            self.identity,
        )

        self.assertEqual(
            set(
                self.user.groups.values_list(
                    "name",
                    flat=True,
                )
            ),
            {
                "BBAMS",
                "pam:leepbioinfo",
                "pam:collaboration",
            },
        )

    @patch(
        "core.middleware.pam_remote_user."
        "grp.getgrgid"
    )
    @patch(
        "core.middleware.pam_remote_user."
        "os.getgrouplist"
    )
    def test_stale_managed_membership_is_removed(
        self,
        mocked_getgrouplist,
        mocked_getgrgid,
    ):
        mocked_getgrouplist.return_value = [
            1300
        ]
        mocked_getgrgid.return_value = (
            self.group_record("newlab")
        )

        _synchronize_pam_groups(
            self.user,
            self.identity,
        )

        self.assertFalse(
            self.user.groups.filter(
                name="pam:oldlab"
            ).exists()
        )
        self.assertTrue(
            self.user.groups.filter(
                name="pam:newlab"
            ).exists()
        )
        self.assertTrue(
            self.user.groups.filter(
                name="BBAMS"
            ).exists()
        )

    @patch(
        "core.middleware.pam_remote_user."
        "os.getgrouplist",
        side_effect=OSError(
            "temporary NSS failure"
        ),
    )
    def test_nss_failure_preserves_existing_memberships(
        self,
        mocked_getgrouplist,
    ):
        _synchronize_pam_groups(
            self.user,
            self.identity,
        )

        self.assertTrue(
            self.user.groups.filter(
                name="pam:oldlab"
            ).exists()
        )
        self.assertTrue(
            self.user.groups.filter(
                name="BBAMS"
            ).exists()
        )

    @patch(
        "core.middleware.pam_remote_user."
        "grp.getgrgid"
    )
    @patch(
        "core.middleware.pam_remote_user."
        "os.getgrouplist"
    )
    def test_sync_does_not_change_privilege_flags(
        self,
        mocked_getgrouplist,
        mocked_getgrgid,
    ):
        mocked_getgrouplist.return_value = [
            1002
        ]
        mocked_getgrgid.return_value = (
            self.group_record("leepbioinfo")
        )

        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

        _synchronize_pam_groups(
            self.user,
            self.identity,
        )
        self.user.refresh_from_db()

        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
