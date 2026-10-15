from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.research_groups.model import ResearchGroup
from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
    can_register_at_storage_location,
)
from core.services.storage_registration_v8 import (
    register_initial_physical_storage,
)
from core.services.storage_sample_intake_v8 import (
    prepare_storage_sample_intake_v8,
)


class StorageWriteAccessV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.admin = User.objects.create_user(
            username="ccalomeno", is_staff=True
        )
        cls.staff = User.objects.create_user(
            username="another-staff-user", is_staff=True
        )
        cls.owner = User.objects.create_user(
            username="physical-owner"
        )
        cls.coordinator = User.objects.create_user(
            username="physical-coordinator"
        )
        cls.member = User.objects.create_user(
            username="physical-group-member"
        )
        cls.outsider = User.objects.create_user(
            username="physical-outsider"
        )

        cls.group = ResearchGroup.objects.create(
            name="Physical Access Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.member)

        cls.personal = StorageWorkspace.objects.create(
            name="Owner Personal Storage",
            scope="personal",
            owner=cls.owner,
        )
        cls.shared = StorageWorkspace.objects.create(
            name="Group Physical Storage",
            scope="group",
            owner=cls.coordinator,
            research_group=cls.group,
        )

        cls.owner_freezer = StorageLocation.objects.create(
            name="Owner Freezer",
            location_type="freezer",
            workspace=cls.personal,
        )
        cls.owner_box = StorageLocation.objects.create(
            name="Owner Box",
            location_type="box",
            parent=cls.owner_freezer,
            workspace=cls.personal,
        )

        cls.group_freezer = StorageLocation.objects.create(
            name="Group Freezer",
            location_type="freezer",
            workspace=cls.shared,
        )
        cls.group_rack = StorageLocation.objects.create(
            name="Group Rack",
            location_type="rack",
            parent=cls.group_freezer,
            workspace=cls.shared,
        )

    def sample(
        self,
        code,
        *,
        owner=None,
        research_group=None,
        path="",
        public=False,
    ):
        return Sample.objects.create(
            sample_id=code,
            sample_type="Other",
            organism_name="Physical Access Test",
            owner=owner or self.owner,
            research_group=research_group,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=public,
            is_embargoed=False,
            storage_location=path,
        )

    def register(self, *, actor, sample, location, position):
        return register_initial_physical_storage(
            actor=actor,
            sample=sample,
            box=location,
            position=position,
            mode="new",
            expected_legacy_path="",
        )

    def test_owner_can_register_in_personal_workspace(self):
        sample = self.sample("WRITE-PERSONAL")

        assignment, movement = self.register(
            actor=self.owner,
            sample=sample,
            location=self.owner_box,
            position="A1",
        )

        self.assertEqual(
            assignment.location_id,
            self.owner_box.pk,
        )
        self.assertEqual(
            movement.movement_type,
            "registration",
        )

    def test_group_member_can_register_group_sample(self):
        sample = self.sample(
            "WRITE-GROUP",
            owner=self.coordinator,
            research_group=self.group,
        )

        assignment, _ = self.register(
            actor=self.member,
            sample=sample,
            location=self.group_rack,
            position="C7",
        )

        self.assertEqual(assignment.position, "C7")

    def test_foreign_workspace_id_cannot_be_used(self):
        sample = self.sample("WRITE-FOREIGN-LOCATION")

        with self.assertRaises(PermissionDenied):
            self.register(
                actor=self.owner,
                sample=sample,
                location=self.group_rack,
                position="B5",
            )

        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=sample
            ).exists()
        )

    def test_foreign_sample_cannot_be_moved_into_own_storage(self):
        sample = self.sample(
            "WRITE-FOREIGN-SAMPLE",
            owner=self.outsider,
            public=True,
        )

        with self.assertRaises(PermissionDenied):
            self.register(
                actor=self.owner,
                sample=sample,
                location=self.owner_box,
                position="B6",
            )

    def test_authorized_inactive_rack_is_validation_error(self):
        sample = self.sample(
            "WRITE-INACTIVE-AUTHORIZED",
            owner=self.coordinator,
            research_group=self.group,
        )

        self.group_rack.is_active = False
        self.group_rack.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.register(
                actor=self.member,
                sample=sample,
                location=self.group_rack,
                position="D7",
            )

        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=sample
            ).exists()
        )

    def test_foreign_inactive_rack_does_not_leak_state(self):
        sample = self.sample("WRITE-INACTIVE-FOREIGN")

        self.group_rack.is_active = False
        self.group_rack.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            self.register(
                actor=self.owner,
                sample=sample,
                location=self.group_rack,
                position="D8",
            )

        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=sample
            ).exists()
        )

    def test_staff_does_not_override_sample_ownership(self):
        sample = self.sample("WRITE-STAFF-DENIED")

        self.assertFalse(
            can_operate_on_sample_storage(
                self.staff, sample
            )
        )

    def test_preview_rejects_foreign_anchor(self):
        with self.assertRaises(PermissionDenied):
            prepare_storage_sample_intake_v8(
                mode="physical",
                storage_text=self.group_rack.full_path,
                anchor_id=self.group_rack.pk,
                positions=["A9"],
                expected_samples=1,
                actor=self.owner,
            )

    def test_group_member_has_group_anchor(self):
        self.assertTrue(
            can_register_at_storage_location(
                self.member,
                self.group_rack,
            )
        )

    def test_outsider_cannot_use_group_anchor(self):
        self.assertFalse(
            can_register_at_storage_location(
                self.outsider,
                self.group_rack,
            )
        )

    def test_post_foreign_destination_returns_403(self):
        sample = self.sample("WRITE-POST-DENIED")

        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("storage_workspace"),
            {
                "action": "assign_sample",
                "sample_id": sample.pk,
                "location_id": self.group_rack.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            SampleStorageAssignment.objects.filter(
                sample=sample
            ).exists()
        )

    def test_public_sample_cannot_be_assigned_by_outsider(self):
        sample = self.sample(
            "WRITE-PUBLIC-DENIED",
            owner=self.outsider,
            public=True,
        )

        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("storage_workspace"),
            {
                "action": "assign_sample",
                "sample_id": sample.pk,
                "location_id": self.owner_box.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
