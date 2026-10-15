"""E1 regression: preview/execution safety parity."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_sample_movement_preview import (
    preview_sample_movements,
)
from core.services.storage_sample_movements import move_sample


class StorageExecutionParityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="e1-parity-owner",
        )

        cls.other = User.objects.create_user(
            username="e1-parity-other",
        )

        cls.source_room = StorageLocation.objects.create(
            name="E1 Source Room",
            location_type="room",
        )

        cls.destination_room = StorageLocation.objects.create(
            name="E1 Destination Room",
            location_type="room",
        )

        cls.source = StorageLocation.objects.create(
            name="E1 Source Box",
            parent=cls.source_room,
            location_type="box",
        )

        cls.destination = StorageLocation.objects.create(
            name="E1 Destination Box",
            parent=cls.destination_room,
            location_type="box",
        )

        cls.sample = Sample.objects.create(
            sample_id="E1-PARITY-001",
            sample_type="Other",
            organism_name="E1 Parity Sample",
            owner=cls.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        cls.assignment = SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.source,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="E1 Movement Parity Workspace",
            scope="personal",
            owner=cls.owner,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.source_room.pk,
                cls.destination_room.pk,
                cls.source.pk,
                cls.destination.pk,
            ]
        ).update(workspace=cls.workspace)

    def preview_request(self, position):
        return {
            "assignment_id": self.assignment.pk,
            "destination_id": self.destination.pk,
            "position": position,
        }

    def execute_request(self, position):
        return move_sample(
            assignment_id=self.assignment.pk,
            destination_id=self.destination.pk,
            position=position,
            expected_location_id=self.source.pk,
            expected_position="P01",
            expected_source_path=self.source.full_path,
            expected_destination_path=self.destination.full_path,
            actor=self.owner,
            reason="E1 parity regression.",
        )

    def create_occupied_slot_with_whitespace(self):
        sample = Sample.objects.create(
            sample_id="E1-PARITY-OCCUPANT",
            sample_type="Other",
            organism_name="E1 Occupant",
            owner=self.other,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        return SampleStorageAssignment.objects.create(
            sample=sample,
            location=self.destination,
            rank=1,
            is_primary=True,
            position=" p03 ",
            status="active",
        )

    def test_inactive_source_can_be_evacuated_by_both_services(self):
        """Preview and execution permit authorized evacuation."""
        self.source_room.is_active = False
        self.source_room.save(update_fields=["is_active"])

        preview = preview_sample_movements(
            moves=[self.preview_request("P04")],
            actor=self.owner,
        )

        self.assertEqual(len(preview["moves"]), 1)
        self.assertEqual(
            preview["moves"][0]["position_after"],
            "P04",
        )

        # Preview must not change the canonical assignment.
        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.location_id,
            self.source.pk,
        )
        self.assertEqual(
            self.assignment.position,
            "P01",
        )

        # Execution must follow the same authorization rule.
        self.execute_request("P04")

        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.location_id,
            self.destination.pk,
        )
        self.assertEqual(
            self.assignment.position,
            "P04",
        )


    def test_preview_normalizes_occupied_position(self):
        self.create_occupied_slot_with_whitespace()

        with self.assertRaises(ValidationError):
            preview_sample_movements(
                moves=[self.preview_request("P03")],
                actor=self.owner,
            )

    def test_execution_normalizes_occupied_position(self):
        self.create_occupied_slot_with_whitespace()

        with self.assertRaises(ValidationError):
            self.execute_request("P03")

    def test_origin_relocated_during_lock_discovery(self):
        """
        Reject a source location that was not part of the
        infrastructure rows locked for this transaction.
        """
        from unittest.mock import patch

        from core.models.samples.storage import StorageMovement
        from core.services import storage_sample_movements as service

        alternative_source = StorageLocation.objects.create(
            name="E1 Alternative Source Box",
            parent=self.source_room,
            location_type="box",
            workspace=self.workspace,
        )

        actual_ancestors = service._ancestors
        race = {"triggered": False}

        def injected_ancestors(location_id):
            result = actual_ancestors(location_id)

            if (
                location_id == self.source.pk
                and not race["triggered"]
            ):
                race["triggered"] = True

                # Simulates a concurrent writer relocating the
                # assignment after initial source discovery.
                SampleStorageAssignment.objects.filter(
                    pk=self.assignment.pk
                ).update(location=alternative_source)

            return result

        with patch.object(
            service,
            "_ancestors",
            side_effect=injected_ancestors,
        ):
            with self.assertRaisesRegex(
                ValidationError,
                "Source location changed during lock acquisition",
            ):
                service.move_sample(
                    assignment_id=self.assignment.pk,
                    destination_id=self.destination.pk,
                    position="P04",
                    expected_location_id=alternative_source.pk,
                    expected_position="P01",
                    expected_source_path=alternative_source.full_path,
                    expected_destination_path=self.destination.full_path,
                    actor=self.owner,
                    reason="E1B simulated concurrent relocation.",
                )

        self.assertTrue(race["triggered"])

        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.location_id,
            self.source.pk,
        )
        self.assertEqual(self.assignment.position, "P01")
        self.assertFalse(StorageMovement.objects.exists())
