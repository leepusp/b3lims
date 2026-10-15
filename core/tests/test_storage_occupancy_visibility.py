from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models.research_groups.model import ResearchGroup

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)


class StorageOccupancyVisibilityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner_a = User.objects.create_user(
            username="occupancy-owner-a"
        )
        cls.owner_b = User.objects.create_user(
            username="occupancy-owner-b"
        )
        # Only the designated V8 global admin can inspect
        # all private Sample assignments across this inventory.
        cls.manager = User.objects.create_superuser(
            username="ccalomeno",
            email="occupancy-admin@example.invalid",
            password="test-only-password",
        )

        cls.coordinator = User.objects.create_user(
            username="occupancy-coordinator",
        )

        cls.group = ResearchGroup.objects.create(
            name="Occupancy Shared Storage Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.owner_a, cls.owner_b)

        cls.workspace_group = StorageWorkspace.objects.create(
            name="Occupancy Shared Group Workspace",
            scope="group",
            owner=cls.coordinator,
            research_group=cls.group,
        )

        room = StorageLocation.objects.create(
            name="Privacy Test Room",
            location_type="room",
            workspace=cls.workspace_group,
        )

        cls.box = StorageLocation.objects.create(
            name="Privacy Test Box",
            location_type="box",
            parent=room,
            workspace=cls.workspace_group,
        )

        for identifier, owner, placements in (
            (
                "VISIBLE-OCCUPANCY-A",
                cls.owner_a,
                ((1, "P01"), (2, "P02")),
            ),
            (
                "PRIVATE-OCCUPANCY-B",
                cls.owner_b,
                ((1, "P03"),),
            ),
        ):
            sample = Sample.objects.create(
                sample_id=identifier,
                sample_type="Other",
                organism_name=identifier,
                owner=owner,
                status="qc",
                aliquot_count=1,
                is_active=True,
                is_public=False,
                is_embargoed=False,
            )

            for rank, position in placements:
                SampleStorageAssignment.objects.create(
                    sample=sample,
                    location=cls.box,
                    rank=rank,
                    is_primary=(rank == 1),
                    position=position,
                    status="active",
                )

    def workspace(self, user):
        self.client.force_login(user)
        response = self.client.get(
            reverse("storage_workspace")
        )
        self.assertEqual(response.status_code, 200)
        return response

    def box_sample_count(self, response):
        rows = response.context["storage_location_rows"]

        box_row = next(
            row for row in rows
            if row["location"].pk == self.box.pk
        )

        return box_row["location"].active_sample_count

    def test_count_is_scoped_to_visible_samples(self):
        owner_a = self.workspace(self.owner_a)
        owner_b = self.workspace(self.owner_b)
        manager = self.workspace(self.manager)

        self.assertEqual(self.box_sample_count(owner_a), 1)
        self.assertEqual(self.box_sample_count(owner_b), 1)
        self.assertEqual(self.box_sample_count(manager), 2)

    def test_occupancy_preserves_assignment_counts(self):
        response = self.workspace(self.owner_a)

        # Two assignments, but only one distinct Sample.
        self.assertEqual(
            response.context["storage_assignment_total"],
            2,
        )
        self.assertEqual(
            self.box_sample_count(response),
            1,
        )

        self.assertContains(
            response,
            "VISIBLE-OCCUPANCY-A",
        )
        self.assertNotContains(
            response,
            "PRIVATE-OCCUPANCY-B",
        )
