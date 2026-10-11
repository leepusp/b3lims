from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    StorageMovement,
    StorageMovementItem,
)
from core.services.storage_movement_history import (
    visible_storage_movements,
)


class StorageMovementHistoryTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner_a = User.objects.create_user(
            username="history-owner-a"
        )
        cls.owner_b = User.objects.create_user(
            username="history-owner-b"
        )
        cls.manager = User.objects.create_user(
            username="history-manager",
            is_staff=True,
        )

        cls.sample_a = cls.make_sample(
            "HISTORY-A-001", cls.owner_a
        )
        cls.sample_b = cls.make_sample(
            "HISTORY-B-001", cls.owner_b
        )

    @staticmethod
    def make_sample(identifier, owner):
        return Sample.objects.create(
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

    def create_movement(self, samples, movement_type="sample_bulk"):
        movement = StorageMovement.objects.create(
            movement_type=movement_type,
            affected_sample_count=len(samples),
            affected_assignment_count=len(samples),
            origin_path="Sala X > Caixa A",
            destination_path="Sala X > Caixa B",
            actor_label="History test",
            reason="History permission regression test",
        )

        for sample in samples:
            StorageMovementItem.objects.create(
                movement=movement,
                sample=sample,
                sample_identifier=sample.sample_id,
                assignment_id_snapshot=100,
                position_before="P01",
                position_after="P02",
                path_before="Sala X > Caixa A",
                path_after="Sala X > Caixa B",
            )

        return movement

    def visible_ids(self, user):
        return {
            movement.pk
            for movement in visible_storage_movements(user)
        }

    def test_owner_sees_own_sample_movement(self):
        movement = self.create_movement(
            [self.sample_a],
            movement_type="sample",
        )

        self.assertIn(
            movement.pk,
            self.visible_ids(self.owner_a),
        )

    def test_other_owner_does_not_see_private_movement(self):
        movement = self.create_movement(
            [self.sample_b],
            movement_type="sample",
        )

        self.assertNotIn(
            movement.pk,
            self.visible_ids(self.owner_a),
        )

    def test_mixed_bulk_event_is_hidden_entirely(self):
        movement = self.create_movement([
            self.sample_a,
            self.sample_b,
        ])

        self.assertNotIn(
            movement.pk,
            self.visible_ids(self.owner_a),
        )
        self.assertNotIn(
            movement.pk,
            self.visible_ids(self.owner_b),
        )

    def test_missing_sample_reference_is_hidden(self):
        movement = self.create_movement([
            self.sample_a,
        ])

        StorageMovementItem.objects.filter(
            movement=movement
        ).update(sample=None)

        self.assertNotIn(
            movement.pk,
            self.visible_ids(self.owner_a),
        )

    def test_empty_container_event_requires_manager(self):
        movement = StorageMovement.objects.create(
            movement_type="container",
            affected_location_count=1,
            affected_sample_count=0,
            affected_assignment_count=0,
            origin_path="Sala X",
            destination_path="Sala Y",
            reason="Move empty container",
        )

        self.assertNotIn(
            movement.pk,
            self.visible_ids(self.owner_a),
        )

        self.assertIn(
            movement.pk,
            self.visible_ids(self.manager),
        )

    def test_anonymous_user_has_no_history(self):
        self.create_movement([self.sample_a])

        self.assertEqual(
            list(visible_storage_movements(AnonymousUser())),
            [],
        )

    def test_workspace_renders_visible_movement(self):
        from django.urls import reverse

        self.create_movement(
            [self.sample_a],
            movement_type="sample",
        )

        self.client.force_login(self.owner_a)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Movement History")
        self.assertContains(response, "HISTORY-A-001")
        self.assertContains(response, "View changes")
        self.assertContains(response, "P01")
        self.assertContains(response, "P02")

    def test_workspace_hides_private_and_mixed_movements(self):
        from django.urls import reverse

        own = self.create_movement(
            [self.sample_a],
            movement_type="sample",
        )

        private = self.create_movement(
            [self.sample_b],
            movement_type="sample",
        )

        mixed = self.create_movement([
            self.sample_a,
            self.sample_b,
        ])

        StorageMovement.objects.filter(
            pk=private.pk
        ).update(reason="PRIVATE-D1-REASON")

        StorageMovement.objects.filter(
            pk=mixed.pk
        ).update(reason="MIXED-D1-REASON")

        self.client.force_login(self.owner_a)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HISTORY-A-001")
        self.assertNotContains(response, "HISTORY-B-001")
        self.assertNotContains(response, "PRIVATE-D1-REASON")
        self.assertNotContains(response, "MIXED-D1-REASON")

        self.assertIn(
            own.pk,
            [m.pk for m in response.context["storage_movements"]],
        )

    def test_workspace_hides_orphaned_snapshot(self):
        from django.urls import reverse

        movement = self.create_movement([self.sample_a])

        StorageMovementItem.objects.filter(
            movement=movement
        ).update(sample=None)

        StorageMovement.objects.filter(
            pk=movement.pk
        ).update(reason="ORPHAN-D1-REASON")

        self.client.force_login(self.owner_a)

        response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ORPHAN-D1-REASON")

    def test_workspace_empty_container_history_for_manager(self):
        from django.urls import reverse

        StorageMovement.objects.create(
            movement_type="container",
            affected_location_count=1,
            affected_sample_count=0,
            affected_assignment_count=0,
            origin_path="Room A",
            destination_path="Room B",
            reason="EMPTY-CONTAINER-D1",
        )

        self.client.force_login(self.owner_a)

        owner_response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertNotContains(
            owner_response,
            "EMPTY-CONTAINER-D1",
        )

        self.client.force_login(self.manager)

        manager_response = self.client.get(
            reverse("storage_workspace")
        )

        self.assertContains(
            manager_response,
            "EMPTY-CONTAINER-D1",
        )
        self.assertContains(
            manager_response,
            "Infrastructure only",
        )
