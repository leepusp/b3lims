from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from core.models import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.research_groups.model import ResearchGroup
from core.models.samples.sample import Sample
from core.models.samples.storage import SampleStorageAssignment, StorageLocation, StorageWorkspace
from core.permissions.storage_workspaces_v8 import can_manage_storage_workspace
from core.services.storage_container_movements import move_storage_container
from core.services.storage_sample_movements import move_sample
from core.services.storage_workspace_infrastructure_v8 import create_storage_location_in_workspace_v8


class BiobankRoleBase(TestCase):
    def setUp(self):
        User = get_user_model()

        self.coordinator = User.objects.create_user("coord", password="x")
        self.editor = User.objects.create_user("editor", password="x")
        self.plain = User.objects.create_user("plain", password="x")
        self.outsider = User.objects.create_user("outsider", password="x")
        self.group = ResearchGroup.objects.create(name="Group", coordinator=self.coordinator)

        self.group.members.add(self.editor, self.plain)

        self.biobank = Biobank.objects.create(name="BB One", owner=self.coordinator)
        self.other = Biobank.objects.create(name="BB Two", owner=self.coordinator)

        BiobankUserRole.objects.create(user=self.editor, biobank=self.biobank, role="editor")
        BiobankUserRole.objects.create(user=self.outsider, biobank=self.biobank, role="manager")

        self.workspace = StorageWorkspace.objects.create(name="Shared", scope="group", owner=self.coordinator, research_group=self.group, biobank=self.biobank)


class WorkspacePermissionTests(BiobankRoleBase):
    def test_group_member_with_biobank_role_can_build_locations(self):
        self.assertTrue(can_manage_storage_workspace(self.editor, self.workspace))

        location = create_storage_location_in_workspace_v8(actor=self.editor, workspace_id=self.workspace.pk, name="Freezer 1", location_type="freezer")

        self.assertEqual(location.workspace_id, self.workspace.pk)

    def test_group_member_without_a_role_cannot(self):
        self.assertFalse(can_manage_storage_workspace(self.plain, self.workspace))

        with self.assertRaises(PermissionDenied):
            create_storage_location_in_workspace_v8(actor=self.plain, workspace_id=self.workspace.pk, name="X", location_type="freezer")

    def test_biobank_role_outside_the_group_does_not_see_the_workspace(self):
        self.assertFalse(can_manage_storage_workspace(self.outsider, self.workspace))

    def test_workspace_without_a_linked_biobank_keeps_the_old_rule(self):
        self.workspace.biobank = None
        self.workspace.save()

        self.assertFalse(can_manage_storage_workspace(self.editor, self.workspace))
        self.assertTrue(can_manage_storage_workspace(self.coordinator, self.workspace))

    def test_only_owner_or_coordinator_link_the_biobank(self):
        self.client.force_login(self.editor)
        self.client.post(reverse("storage_workspace"), {"action": "set_storage_biobank_v8", "workspace_id": self.workspace.pk, "biobank_id": self.other.pk})
        self.workspace.refresh_from_db()

        self.assertEqual(self.workspace.biobank, self.biobank)

        self.client.force_login(self.coordinator)
        self.client.post(reverse("storage_workspace"), {"action": "set_storage_biobank_v8", "workspace_id": self.workspace.pk, "biobank_id": self.other.pk})
        self.workspace.refresh_from_db()

        self.assertEqual(self.workspace.biobank, self.other)


class CrossWorkspaceMoveTests(BiobankRoleBase):
    def setUp(self):
        super().setUp()

        self.mine = StorageWorkspace.objects.create(name="Mine", scope="personal", owner=self.coordinator, biobank=self.other)
        self.box = StorageLocation.objects.create(name="Box A", location_type="box", workspace=self.workspace)
        self.target = StorageLocation.objects.create(name="Shelf", location_type="rack", workspace=self.mine)
        self.sample = Sample.objects.create(sample_id="XW-1", sample_type="Other", organism_name="x", owner=self.coordinator, status="qc", aliquot_count=1, is_active=True, biobank=self.biobank)
        self.assignment = SampleStorageAssignment.objects.create(sample=self.sample, location=self.box, rank=1, is_primary=True, position="P01", status="active")

    def test_container_moves_to_another_workspace_with_its_subtree_and_samples(self):
        child = StorageLocation.objects.create(name="Tray", location_type="box", parent=self.box, workspace=self.workspace)

        move_storage_container(container=self.box, destination=self.target, actor=self.coordinator, expected_parent_id=None, reason="reorganise")
        self.box.refresh_from_db()
        child.refresh_from_db()
        self.sample.refresh_from_db()
        self.assignment.refresh_from_db()

        self.assertEqual((self.box.workspace_id, child.workspace_id, self.box.parent_id), (self.mine.pk, self.mine.pk, self.target.pk))
        self.assertEqual(self.assignment.location_id, self.box.pk)
        self.assertEqual(self.sample.biobank, self.other)

    def test_a_user_who_manages_only_one_side_is_refused(self):
        with self.assertRaises(PermissionDenied):
            move_storage_container(container=self.box, destination=self.target, actor=self.editor, expected_parent_id=None, reason="no")

    def test_sample_moving_to_the_storage_of_another_biobank_follows_it(self):
        spot = StorageLocation.objects.create(name="Spot", location_type="box", workspace=self.mine)

        move_sample(
            assignment_id=self.assignment.pk, destination_id=spot.pk, position="A1",
            expected_location_id=self.box.pk, expected_position="P01",
            expected_source_path=self.box.full_path, expected_destination_path=spot.full_path,
            actor=self.coordinator, reason="to bb two",
        )
        self.sample.refresh_from_db()

        self.assertEqual(self.sample.biobank, self.other)
