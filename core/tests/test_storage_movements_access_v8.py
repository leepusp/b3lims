from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from core.models.research_groups.model import ResearchGroup
from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_sample_movement_preview import (
    preview_sample_movements,
)
from core.permissions.storage_movements_v8 import (
    authorize_sample_storage_move_v8,
    authorize_storage_container_move_v8,
)


class StorageMovementsAccessV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.admin = User.objects.create_user(
            username="ccalomeno",
            is_staff=True,
        )
        cls.owner = User.objects.create_user(
            username="movement-owner-v8",
        )
        cls.coordinator = User.objects.create_user(
            username="movement-coordinator-v8",
        )
        cls.member = User.objects.create_user(
            username="movement-member-v8",
        )
        cls.outsider = User.objects.create_user(
            username="movement-outsider-v8",
        )

        cls.group = ResearchGroup.objects.create(
            name="Movement Authorization Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.member)

        cls.personal = StorageWorkspace.objects.create(
            name="Movement Personal Workspace",
            scope="personal",
            owner=cls.owner,
        )
        cls.shared = StorageWorkspace.objects.create(
            name="Movement Shared Workspace",
            scope="group",
            owner=cls.coordinator,
            research_group=cls.group,
        )

        cls.personal_freezer = StorageLocation.objects.create(
            name="Movement Personal Freezer",
            location_type="freezer",
            workspace=cls.personal,
        )
        cls.personal_box_a = StorageLocation.objects.create(
            name="Movement Personal Box A",
            location_type="box",
            parent=cls.personal_freezer,
            workspace=cls.personal,
        )
        cls.personal_box_b = StorageLocation.objects.create(
            name="Movement Personal Box B",
            location_type="box",
            parent=cls.personal_freezer,
            workspace=cls.personal,
        )

        cls.group_freezer = StorageLocation.objects.create(
            name="Movement Group Freezer",
            location_type="freezer",
            workspace=cls.shared,
        )
        cls.group_rack = StorageLocation.objects.create(
            name="Movement Group Rack",
            location_type="rack",
            parent=cls.group_freezer,
            workspace=cls.shared,
        )
        cls.group_box = StorageLocation.objects.create(
            name="Movement Group Box",
            location_type="box",
            parent=cls.group_freezer,
            workspace=cls.shared,
        )

    def make_assignment(
        self,
        code,
        *,
        owner=None,
        group=None,
        location=None,
        public=False,
    ):
        sample = Sample.objects.create(
            sample_id=code,
            sample_type="Other",
            organism_name="Movement Test",
            owner=owner or self.owner,
            research_group=group,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=public,
            is_embargoed=False,
        )

        return SampleStorageAssignment.objects.create(
            sample=sample,
            location=location or self.personal_box_a,
            rank=1,
            is_primary=True,
            status="active",
            position="A1",
        )

    def test_preview_accepts_authorized_personal_transfer(self):
        assignment = self.make_assignment(
            "PREVIEW-OWNER-V8"
        )

        result = preview_sample_movements(
            actor=self.owner,
            moves=[{
                "assignment_id": assignment.pk,
                "destination_id": self.personal_box_b.pk,
                "position": "B2",
            }],
        )

        self.assertTrue(result["preview_only"])
        self.assertEqual(
            result["affected_assignment_count"],
            1,
        )

    def test_preview_rejects_foreign_destination(self):
        assignment = self.make_assignment(
            "PREVIEW-FOREIGN-V8"
        )

        with self.assertRaises(PermissionDenied):
            preview_sample_movements(
                actor=self.owner,
                moves=[{
                    "assignment_id": assignment.pk,
                    "destination_id": self.group_box.pk,
                    "position": "B3",
                }],
            )

    def test_preview_rejects_foreign_source(self):
        assignment = self.make_assignment(
            "PREVIEW-FOREIGN-SOURCE-V8",
            location=self.group_rack,
        )

        with self.assertRaises(PermissionDenied):
            preview_sample_movements(
                actor=self.owner,
                moves=[{
                    "assignment_id": assignment.pk,
                    "destination_id": self.personal_box_b.pk,
                    "position": "B4",
                }],
            )

    def test_preview_allows_evacuation_from_inactive_source(self):
        assignment = self.make_assignment(
            "PREVIEW-EVACUATION-V8"
        )

        self.personal_box_a.is_active = False
        self.personal_box_a.save(
            update_fields=["is_active"]
        )

        result = preview_sample_movements(
            actor=self.owner,
            moves=[{
                "assignment_id": assignment.pk,
                "destination_id": self.personal_box_b.pk,
                "position": "B5",
            }],
        )

        self.assertEqual(
            result["affected_assignment_count"],
            1,
        )

    def test_preview_does_not_accept_public_sample_as_permission(self):
        assignment = self.make_assignment(
            "PREVIEW-PUBLIC-V8",
            owner=self.outsider,
            public=True,
        )

        with self.assertRaises(PermissionDenied):
            preview_sample_movements(
                actor=self.owner,
                moves=[{
                    "assignment_id": assignment.pk,
                    "destination_id": self.personal_box_b.pk,
                    "position": "B6",
                }],
            )

    def test_owner_can_move_personal_sample(self):
        assignment = self.make_assignment("MOVE-OWNER-V8")

        self.assertTrue(
            authorize_sample_storage_move_v8(
                actor=self.owner,
                assignment=assignment,
                destination=self.personal_box_b,
            )
        )

    def test_group_member_can_move_authorized_group_sample(self):
        assignment = self.make_assignment(
            "MOVE-GROUP-V8",
            owner=self.coordinator,
            group=self.group,
            location=self.group_rack,
        )

        self.assertTrue(
            authorize_sample_storage_move_v8(
                actor=self.member,
                assignment=assignment,
                destination=self.group_box,
            )
        )

    def test_foreign_destination_is_denied(self):
        assignment = self.make_assignment("MOVE-FOREIGN-V8")

        with self.assertRaises(PermissionDenied):
            authorize_sample_storage_move_v8(
                actor=self.owner,
                assignment=assignment,
                destination=self.group_box,
            )

    def test_foreign_inactive_destination_stays_hidden(self):
        assignment = self.make_assignment(
            "MOVE-FOREIGN-INACTIVE-V8"
        )

        self.group_box.is_active = False
        self.group_box.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            authorize_sample_storage_move_v8(
                actor=self.owner,
                assignment=assignment,
                destination=self.group_box,
            )

    def test_foreign_source_is_denied(self):
        assignment = self.make_assignment(
            "MOVE-FOREIGN-SOURCE-V8",
            location=self.group_rack,
        )

        with self.assertRaises(PermissionDenied):
            authorize_sample_storage_move_v8(
                actor=self.owner,
                assignment=assignment,
                destination=self.personal_box_b,
            )

    def test_public_sample_does_not_grant_movement_access(self):
        assignment = self.make_assignment(
            "MOVE-PUBLIC-V8",
            owner=self.outsider,
            public=True,
        )

        with self.assertRaises(PermissionDenied):
            authorize_sample_storage_move_v8(
                actor=self.owner,
                assignment=assignment,
                destination=self.personal_box_b,
            )

    def test_inactive_source_can_be_evacuated(self):
        assignment = self.make_assignment(
            "MOVE-INACTIVE-SOURCE-V8"
        )

        self.personal_box_a.is_active = False
        self.personal_box_a.save(update_fields=["is_active"])

        self.assertTrue(
            authorize_sample_storage_move_v8(
                actor=self.owner,
                assignment=assignment,
                destination=self.personal_box_b,
            )
        )

    def test_group_coordinator_can_move_group_container(self):
        self.assertTrue(
            authorize_storage_container_move_v8(
                actor=self.coordinator,
                container=self.group_rack,
                destination=self.group_box,
            )
        )

    def test_group_member_cannot_move_group_container(self):
        with self.assertRaises(PermissionDenied):
            authorize_storage_container_move_v8(
                actor=self.member,
                container=self.group_rack,
                destination=self.group_box,
            )

    def test_global_admin_cannot_silently_change_ownership(self):
        with self.assertRaises(PermissionDenied):
            authorize_storage_container_move_v8(
                actor=self.admin,
                container=self.personal_box_a,
                destination=self.group_freezer,
            )

    def test_foreign_descendant_blocks_container_move(self):
        StorageLocation.objects.create(
            name="Foreign Descendant V8",
            location_type="box",
            parent=self.personal_box_a,
            workspace=self.shared,
        )

        with self.assertRaises(PermissionDenied):
            authorize_storage_container_move_v8(
                actor=self.owner,
                container=self.personal_box_a,
                destination=self.personal_box_b,
            )

    def test_unrelated_user_cannot_move_private_container(self):
        with self.assertRaises(PermissionDenied):
            authorize_storage_container_move_v8(
                actor=self.outsider,
                container=self.personal_box_a,
                destination=self.personal_box_b,
            )
