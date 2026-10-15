from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from core.models.research_groups.model import ResearchGroup
from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.permissions.storage_workspaces_v8 import (
    can_manage_storage_workspace,
    can_register_in_storage_workspace,
    can_view_storage_location,
    is_storage_global_admin,
    visible_storage_locations_for_user,
    visible_storage_workspaces_for_user,
)
from core.services.storage_anchor_catalog_v8 import (
    build_storage_anchor_catalog,
)
from core.services.storage_workspaces_v8 import (
    create_storage_workspace_v8,
)


class StorageWorkspacesV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.admin = User.objects.create_user(
            username="ccalomeno",
            is_staff=True,
        )
        cls.staff_other = User.objects.create_user(
            username="unrelated-staff",
            is_staff=True,
        )
        cls.owner = User.objects.create_user(
            username="personal-owner",
        )
        cls.coordinator = User.objects.create_user(
            username="group-coordinator",
        )
        cls.member = User.objects.create_user(
            username="group-member",
        )
        cls.outsider = User.objects.create_user(
            username="other-laboratory-user",
        )

        cls.group = ResearchGroup.objects.create(
            name="Storage Test Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.member)

        cls.personal = StorageWorkspace.objects.create(
            name="Private storage",
            scope="personal",
            owner=cls.owner,
        )
        cls.shared = StorageWorkspace.objects.create(
            name="Shared group storage",
            scope="group",
            owner=cls.coordinator,
            research_group=cls.group,
        )

        cls.private_freezer = StorageLocation.objects.create(
            name="Private Freezer",
            location_type="freezer",
            workspace=cls.personal,
        )
        cls.private_box = StorageLocation.objects.create(
            name="Private Box",
            location_type="box",
            parent=cls.private_freezer,
            workspace=cls.personal,
        )
        cls.shared_freezer = StorageLocation.objects.create(
            name="Group Freezer",
            location_type="freezer",
            workspace=cls.shared,
        )
        cls.legacy = StorageLocation.objects.create(
            name="Unscoped Legacy Freezer",
            location_type="freezer",
        )

    def test_only_designated_admin_has_global_access(self):
        self.assertTrue(is_storage_global_admin(self.admin))
        self.assertFalse(
            is_storage_global_admin(self.staff_other)
        )
        self.assertFalse(is_storage_global_admin(self.owner))

    def test_personal_storage_is_private(self):
        self.assertTrue(
            can_view_storage_location(
                self.owner, self.private_box
            )
        )
        self.assertFalse(
            can_view_storage_location(
                self.member, self.private_box
            )
        )

    def test_group_members_can_view_and_register(self):
        self.assertTrue(
            can_view_storage_location(
                self.member, self.shared_freezer
            )
        )
        self.assertTrue(
            can_register_in_storage_workspace(
                self.member, self.shared
            )
        )

    def test_group_management_is_coordinator_only(self):
        self.assertTrue(
            can_manage_storage_workspace(
                self.coordinator, self.shared
            )
        )
        self.assertFalse(
            can_manage_storage_workspace(
                self.member, self.shared
            )
        )

    def test_unrelated_staff_cannot_view_all_locations(self):
        self.assertEqual(
            list(
                visible_storage_locations_for_user(
                    self.staff_other
                )
            ),
            [],
        )

    def test_unscoped_legacy_storage_is_admin_only(self):
        self.assertFalse(
            can_view_storage_location(
                self.owner, self.legacy
            )
        )
        self.assertTrue(
            can_view_storage_location(
                self.admin, self.legacy
            )
        )

    def test_location_catalog_is_isolated(self):
        owner_names = {
            item["name"]
            for item in build_storage_anchor_catalog(
                user=self.owner
            )
        }

        member_names = {
            item["name"]
            for item in build_storage_anchor_catalog(
                user=self.member
            )
        }

        self.assertIn("Private Box", owner_names)
        self.assertNotIn("Group Freezer", owner_names)

        self.assertIn("Group Freezer", member_names)
        self.assertNotIn("Private Box", member_names)

    def test_administrator_sees_all_catalogs(self):
        names = {
            item["name"]
            for item in build_storage_anchor_catalog(
                user=self.admin
            )
        }

        self.assertIn("Private Box", names)
        self.assertIn("Group Freezer", names)
        self.assertIn("Unscoped Legacy Freezer", names)

    def test_outsider_cannot_see_group_workspace(self):
        ids = set(
            visible_storage_workspaces_for_user(
                self.outsider
            ).values_list("pk", flat=True)
        )

        self.assertNotIn(self.shared.pk, ids)

    def test_invalid_cross_workspace_child_is_hidden(self):
        mixed = StorageLocation.objects.create(
            name="Invalid Cross Workspace Child",
            parent=self.private_freezer,
            workspace=self.shared,
            location_type="box",
        )

        self.assertFalse(
            can_view_storage_location(
                self.member, mixed
            )
        )

        ids = set(
            visible_storage_locations_for_user(
                self.member
            ).values_list("pk", flat=True)
        )

        self.assertNotIn(mixed.pk, ids)

    def test_member_cannot_create_group_workspace(self):
        with self.assertRaises(PermissionDenied):
            create_storage_workspace_v8(
                actor=self.member,
                name="Unauthorized Group Workspace",
                scope="group",
                research_group_id=self.group.pk,
            )

    def test_coordinator_can_create_group_workspace(self):
        workspace = create_storage_workspace_v8(
            actor=self.coordinator,
            name="Authorized Group Workspace",
            scope="group",
            research_group_id=self.group.pk,
        )

        self.assertEqual(
            workspace.research_group_id,
            self.group.pk,
        )

    def test_personal_workspace_creation(self):
        workspace = create_storage_workspace_v8(
            actor=self.owner,
            name="My Storage",
            scope="personal",
        )

        self.assertEqual(workspace.owner_id, self.owner.pk)
        self.assertIsNone(workspace.research_group_id)
