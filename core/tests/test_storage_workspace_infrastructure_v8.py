from django.contrib.auth import get_user_model
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.test import TestCase

from core.models.research_groups.model import ResearchGroup
from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_workspace_infrastructure_v8 import (
    create_storage_location_in_workspace_v8,
    update_storage_location_in_workspace_v8,
    set_storage_location_active_in_workspace_v8,
)


class StorageWorkspaceInfrastructureV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.admin = User.objects.create_user(
            username="ccalomeno",
            is_staff=True,
        )
        cls.owner = User.objects.create_user(
            username="v8-infrastructure-owner",
        )
        cls.coordinator = User.objects.create_user(
            username="v8-infrastructure-coordinator",
        )
        cls.member = User.objects.create_user(
            username="v8-infrastructure-member",
        )
        cls.staff = User.objects.create_user(
            username="v8-infrastructure-staff",
            is_staff=True,
        )
        cls.outsider = User.objects.create_user(
            username="v8-infrastructure-outsider",
        )

        cls.group = ResearchGroup.objects.create(
            name="V8 Infrastructure Test Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.member)

        cls.personal = StorageWorkspace.objects.create(
            name="Infrastructure Personal",
            owner=cls.owner,
            scope="personal",
        )
        cls.shared = StorageWorkspace.objects.create(
            name="Infrastructure Group",
            owner=cls.coordinator,
            scope="group",
            research_group=cls.group,
        )

    def create(self, *, actor=None, workspace=None,
               parent_id=None, name="Freezer A",
               location_type="freezer"):
        return create_storage_location_in_workspace_v8(
            actor=actor or self.owner,
            workspace_id=(workspace or self.personal).pk,
            name=name,
            location_type=location_type,
            parent_id=parent_id,
        )

    def test_owner_creates_personal_freezer(self):
        freezer = self.create()

        self.assertEqual(
            freezer.workspace_id,
            self.personal.pk,
        )
        self.assertIsNone(freezer.parent_id)

    def test_owner_creates_nested_physical_box(self):
        freezer = self.create()
        box = self.create(
            parent_id=freezer.pk,
            name="Box A1",
            location_type="box",
        )

        self.assertEqual(box.parent_id, freezer.pk)
        self.assertEqual(
            box.workspace_id,
            self.personal.pk,
        )

    def test_group_coordinator_can_create_storage(self):
        freezer = self.create(
            actor=self.coordinator,
            workspace=self.shared,
        )

        self.assertEqual(
            freezer.workspace_id,
            self.shared.pk,
        )

    def test_group_member_cannot_change_infrastructure(self):
        with self.assertRaises(PermissionDenied):
            self.create(
                actor=self.member,
                workspace=self.shared,
            )

    def test_unrelated_staff_has_no_global_access(self):
        with self.assertRaises(PermissionDenied):
            self.create(
                actor=self.staff,
                workspace=self.personal,
            )

    def test_outsider_cannot_create_in_another_workspace(self):
        before = StorageLocation.objects.count()

        with self.assertRaises(PermissionDenied):
            self.create(
                actor=self.outsider,
            )

        self.assertEqual(
            StorageLocation.objects.count(),
            before,
        )

    def test_global_admin_can_manage_group_workspace(self):
        freezer = self.create(
            actor=self.admin,
            workspace=self.shared,
        )

        self.assertEqual(
            freezer.workspace_id,
            self.shared.pk,
        )

    def test_cross_workspace_parent_is_rejected(self):
        freezer = self.create()

        with self.assertRaises(PermissionDenied):
            self.create(
                actor=self.coordinator,
                workspace=self.shared,
                parent_id=freezer.pk,
                name="Foreign Box",
                location_type="box",
            )

    def test_inactive_parent_is_rejected(self):
        freezer = self.create()
        freezer.is_active = False
        freezer.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.create(
                parent_id=freezer.pk,
                name="Inactive Box",
                location_type="box",
            )

    def test_position_is_not_physical_infrastructure(self):
        with self.assertRaises(ValidationError):
            self.create(
                name="B5",
                location_type="position",
            )

    def test_duplicate_root_name_is_rejected(self):
        self.create(name="Freezer A")

        with self.assertRaises(ValidationError):
            self.create(name="freezer a")

    def test_owner_updates_location(self):
        freezer = self.create()

        changed = update_storage_location_in_workspace_v8(
            actor=self.owner,
            location_id=freezer.pk,
            name="Freezer B",
            location_type="freezer",
            rank=2,
            notes="Updated through workspace policy",
        )

        self.assertEqual(changed.name, "Freezer B")
        self.assertEqual(
            changed.workspace_id,
            self.personal.pk,
        )

    def test_member_cannot_update_group_location(self):
        freezer = self.create(
            actor=self.coordinator,
            workspace=self.shared,
        )

        with self.assertRaises(PermissionDenied):
            update_storage_location_in_workspace_v8(
                actor=self.member,
                location_id=freezer.pk,
                name="Unauthorized",
                location_type="freezer",
            )

        freezer.refresh_from_db()
        self.assertEqual(freezer.name, "Freezer A")

    def test_owner_can_deactivate_personal_storage(self):
        freezer = self.create()

        changed = set_storage_location_active_in_workspace_v8(
            actor=self.owner,
            location_id=freezer.pk,
            is_active=False,
        )

        self.assertFalse(changed.is_active)

    def test_outsider_cannot_deactivate_storage(self):
        freezer = self.create()

        with self.assertRaises(PermissionDenied):
            set_storage_location_active_in_workspace_v8(
                actor=self.outsider,
                location_id=freezer.pk,
                is_active=False,
            )

        freezer.refresh_from_db()
        self.assertTrue(freezer.is_active)
