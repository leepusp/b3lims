from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from core.models.research_groups.model import ResearchGroup
from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageWorkspace,
)
from core.services.storage_container_movements import (
    move_storage_container,
)
from core.services.storage_sample_movements import (
    move_sample,
    move_samples_bulk,
)


class StorageMovementExecutionV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="exec-v8-owner"
        )
        cls.coordinator = User.objects.create_user(
            username="exec-v8-coordinator"
        )
        cls.member = User.objects.create_user(
            username="exec-v8-member"
        )
        cls.outsider = User.objects.create_user(
            username="exec-v8-outsider"
        )
        cls.staff = User.objects.create_user(
            username="exec-v8-staff", is_staff=True
        )

        cls.group = ResearchGroup.objects.create(
            name="Execution V8 Research Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.member)

        cls.personal = StorageWorkspace.objects.create(
            name="Execution Personal Workspace",
            owner=cls.owner,
            scope="personal",
        )
        cls.shared = StorageWorkspace.objects.create(
            name="Execution Group Workspace",
            owner=cls.coordinator,
            scope="group",
            research_group=cls.group,
        )

        cls.freezer_a = StorageLocation.objects.create(
            name="Execution Freezer A",
            location_type="freezer",
            workspace=cls.personal,
        )
        cls.freezer_b = StorageLocation.objects.create(
            name="Execution Freezer B",
            location_type="freezer",
            workspace=cls.personal,
        )
        cls.box_a = StorageLocation.objects.create(
            name="Execution Box A",
            location_type="box",
            parent=cls.freezer_a,
            workspace=cls.personal,
        )
        cls.box_b = StorageLocation.objects.create(
            name="Execution Box B",
            location_type="box",
            parent=cls.freezer_a,
            workspace=cls.personal,
        )

        cls.group_freezer = StorageLocation.objects.create(
            name="Execution Group Freezer",
            location_type="freezer",
            workspace=cls.shared,
        )
        cls.group_rack = StorageLocation.objects.create(
            name="Execution Group Rack",
            location_type="rack",
            parent=cls.group_freezer,
            workspace=cls.shared,
        )
        cls.group_box = StorageLocation.objects.create(
            name="Execution Group Box",
            location_type="box",
            parent=cls.group_freezer,
            workspace=cls.shared,
        )

    def assignment(
        self, code, *, owner=None, group=None,
        location=None, position="A1",
    ):
        sample = Sample.objects.create(
            sample_id=code,
            sample_type="Other",
            organism_name="Execution Test",
            owner=owner or self.owner,
            research_group=group,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )
        return SampleStorageAssignment.objects.create(
            sample=sample,
            location=location or self.box_a,
            position=position,
            rank=1,
            is_primary=True,
            status="active",
        )

    def movement_fields(self, assignment, destination, position):
        return {
            "assignment_id": assignment.pk,
            "destination_id": destination.pk,
            "position": position,
            "expected_location_id": assignment.location_id,
            "expected_position": assignment.position,
            "expected_source_path": assignment.location.full_path,
            "expected_destination_path": destination.full_path,
        }

    def execute(self, actor, assignment, destination, position):
        return move_sample(
            actor=actor,
            reason="Authorized workspace movement test",
            **self.movement_fields(
                assignment, destination, position
            ),
        )

    def test_owner_moves_personal_sample(self):
        assignment = self.assignment("EXEC-PERSONAL-V8")

        movement = self.execute(
            self.owner, assignment, self.box_b, "B1"
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.location_id, self.box_b.pk)
        self.assertEqual(assignment.position, "B1")
        self.assertEqual(movement.movement_type, "sample")

    def test_individual_destination_snapshot_is_recorded(self):
        assignment = self.assignment(
            "EXEC-DEST-SNAPSHOT-V8",
            position="A1",
        )

        movement = self.execute(
            self.owner,
            assignment,
            self.box_b,
            "B1",
        )

        item = movement.items.get()

        self.assertEqual(
            item.location_id_snapshot,
            self.box_a.pk,
        )
        self.assertEqual(
            item.destination_location_id_snapshot,
            self.box_b.pk,
        )

    def test_bulk_records_each_distinct_destination(self):
        first = self.assignment(
            "EXEC-BULK-SNAPSHOT-1-V8",
            position="A1",
        )
        second = self.assignment(
            "EXEC-BULK-SNAPSHOT-2-V8",
            position="A2",
        )

        movement = move_samples_bulk(
            actor=self.owner,
            reason="Validate per-item destination snapshots",
            moves=[
                self.movement_fields(
                    first,
                    self.box_b,
                    "B1",
                ),
                self.movement_fields(
                    second,
                    self.box_a,
                    "A3",
                ),
            ],
        )

        snapshots = {
            item.assignment_id_snapshot: (
                item.location_id_snapshot,
                item.destination_location_id_snapshot,
            )
            for item in movement.items.all()
        }

        self.assertEqual(
            snapshots,
            {
                first.pk: (self.box_a.pk, self.box_b.pk),
                second.pk: (self.box_a.pk, self.box_a.pk),
            },
        )

        self.assertIsNone(
            movement.destination_location_id,
        )

    def test_container_preserves_item_location_snapshot(self):
        self.assignment(
            "EXEC-CONTAINER-SNAPSHOT-V8",
            position="A1",
        )

        movement = move_storage_container(
            container=self.box_a,
            destination=self.freezer_b,
            actor=self.owner,
            expected_parent_id=self.freezer_a.pk,
            expected_origin_path=self.box_a.full_path,
            expected_destination_path=(
                f"{self.freezer_b.full_path} > {self.box_a.name}"
            ),
            reason="Validate container destination snapshot",
        )

        item = movement.items.get()

        self.assertEqual(
            item.location_id_snapshot,
            self.box_a.pk,
        )
        self.assertEqual(
            item.destination_location_id_snapshot,
            self.box_a.pk,
        )

        self.assertEqual(
            movement.destination_location_id,
            self.freezer_b.pk,
        )

    def test_group_member_moves_shared_sample(self):
        assignment = self.assignment(
            "EXEC-GROUP-V8",
            owner=self.coordinator,
            group=self.group,
            location=self.group_rack,
        )

        movement = self.execute(
            self.member, assignment, self.group_box, "B2"
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.location_id, self.group_box.pk)
        self.assertEqual(movement.movement_type, "sample")

    def test_foreign_destination_rejected_without_audit(self):
        assignment = self.assignment("EXEC-FOREIGN-DEST-V8")
        before = StorageMovement.objects.count()

        with self.assertRaises(PermissionDenied):
            self.execute(
                self.owner, assignment, self.group_box, "C1"
            )

        assignment.refresh_from_db()
        self.assertEqual(assignment.location_id, self.box_a.pk)
        self.assertEqual(StorageMovement.objects.count(), before)

    def test_staff_cannot_move_other_users_sample(self):
        assignment = self.assignment("EXEC-STAFF-V8")
        before = StorageMovement.objects.count()

        with self.assertRaises(PermissionDenied):
            self.execute(
                self.staff, assignment, self.box_b, "C2"
            )

        assignment.refresh_from_db()
        self.assertEqual(assignment.location_id, self.box_a.pk)
        self.assertEqual(StorageMovement.objects.count(), before)

    def test_bulk_transfer_is_atomic_on_access_denial(self):
        valid = self.assignment(
            "EXEC-BULK-VALID-V8", position="A1"
        )
        foreign = self.assignment(
            "EXEC-BULK-FOREIGN-V8",
            owner=self.outsider,
            position="A2",
        )
        before = StorageMovement.objects.count()

        moves = [
            self.movement_fields(valid, self.box_b, "D1"),
            self.movement_fields(foreign, self.box_b, "D2"),
        ]

        with self.assertRaises(PermissionDenied):
            move_samples_bulk(
                moves=moves,
                actor=self.owner,
                reason="Atomic bulk security test",
            )

        valid.refresh_from_db()
        foreign.refresh_from_db()

        self.assertEqual(valid.location_id, self.box_a.pk)
        self.assertEqual(foreign.location_id, self.box_a.pk)
        self.assertEqual(StorageMovement.objects.count(), before)

    def test_authorized_evacuation_from_inactive_source(self):
        assignment = self.assignment("EXEC-EVACUATION-V8")

        self.box_a.is_active = False
        self.box_a.save(update_fields=["is_active"])

        self.execute(
            self.owner, assignment, self.box_b, "E1"
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.location_id, self.box_b.pk)

    def test_owner_moves_container_with_owned_sample(self):
        assignment = self.assignment("EXEC-CONTAINER-V8")

        movement = move_storage_container(
            container=self.box_a,
            destination=self.freezer_b,
            actor=self.owner,
            expected_parent_id=self.freezer_a.pk,
            expected_origin_path=self.box_a.full_path,
            expected_destination_path=(
                f"{self.freezer_b.full_path} > {self.box_a.name}"
            ),
            reason="Workspace container movement test",
        )

        self.box_a.refresh_from_db()
        assignment.refresh_from_db()

        self.assertEqual(self.box_a.parent_id, self.freezer_b.pk)
        self.assertEqual(assignment.location_id, self.box_a.pk)
        self.assertEqual(movement.movement_type, "container")

    def test_container_with_foreign_sample_is_rejected(self):
        self.assignment(
            "EXEC-CONTAINER-FOREIGN-V8",
            owner=self.outsider,
        )
        before = StorageMovement.objects.count()

        with self.assertRaises(PermissionDenied):
            move_storage_container(
                container=self.box_a,
                destination=self.freezer_b,
                actor=self.owner,
                expected_parent_id=self.freezer_a.pk,
                expected_origin_path=self.box_a.full_path,
                expected_destination_path=(
                    f"{self.freezer_b.full_path} > {self.box_a.name}"
                ),
                reason="Unauthorized custody transfer test",
            )

        self.box_a.refresh_from_db()

        self.assertEqual(
            self.box_a.parent_id,
            self.freezer_a.pk,
        )
        self.assertEqual(StorageMovement.objects.count(), before)

    def test_group_coordinator_can_move_empty_group_rack(self):
        movement = move_storage_container(
            container=self.group_rack,
            destination=self.group_box,
            actor=self.coordinator,
            expected_parent_id=self.group_freezer.pk,
            expected_origin_path=self.group_rack.full_path,
            expected_destination_path=(
                f"{self.group_box.full_path} > "
                f"{self.group_rack.name}"
            ),
            reason="Group infrastructure movement test",
        )

        self.group_rack.refresh_from_db()
        self.assertEqual(
            self.group_rack.parent_id,
            self.group_box.pk,
        )
        self.assertEqual(movement.movement_type, "container")

    def test_container_preview_requires_workspace_permission(self):
        self.client.force_login(self.outsider)

        response = self.client.get(
            reverse("storage_workspace"),
            {
                "preview_container": "1",
                "container_id": self.box_a.pk,
                "destination_id": self.freezer_b.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
