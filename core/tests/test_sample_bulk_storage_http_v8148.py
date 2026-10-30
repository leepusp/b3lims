"""End-to-end HTTP safety tests for selected-Sample physical storage."""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageMovement,
    StorageMovementItem,
    StorageWorkspace,
)


class SelectedSampleStorageHTTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="b3-bulk-owner")
        cls.other = User.objects.create_user(username="b3-bulk-other")
        cls.workspace = StorageWorkspace.objects.create(
            name="Bulk HTTP workspace", scope="personal", owner=cls.owner,
        )
        cls.foreign_workspace = StorageWorkspace.objects.create(
            name="Foreign HTTP workspace", scope="personal", owner=cls.other,
        )
        cls.freezer = StorageLocation.objects.create(
            name="Bulk Freezer", location_type="freezer",
            workspace=cls.workspace,
        )
        cls.source = StorageLocation.objects.create(
            name="Bulk Source", location_type="box",
            workspace=cls.workspace, parent=cls.freezer,
        )
        cls.destination = StorageLocation.objects.create(
            name="Bulk Destination", location_type="box",
            workspace=cls.workspace, parent=cls.freezer,
        )
        cls.foreign_destination = StorageLocation.objects.create(
            name="Foreign Destination", location_type="box",
            workspace=cls.foreign_workspace,
        )
        cls.a = cls.make_sample("B3-BULK-A", cls.owner)
        cls.b = cls.make_sample("B3-BULK-B", cls.owner)
        cls.c = cls.make_sample("B3-BULK-C", cls.owner)
        cls.foreign_sample = cls.make_sample("B3-BULK-FOREIGN", cls.other)

    @staticmethod
    def make_sample(identifier, owner):
        return Sample.objects.create(
            sample_id=identifier, sample_type="Other",
            organism_name=identifier, owner=owner,
            status="available", is_active=True, is_public=False,
        )

    @staticmethod
    def client_path(name):
        path = reverse(name)
        prefix = str(getattr(settings, "FORCE_SCRIPT_NAME", "") or "")
        return (path[len(prefix):] or "/") if prefix and path.startswith(prefix) else path

    def setUp(self):
        self.client.force_login(self.owner)
        self.path = self.client_path("sample_bulk_storage")

    def initial_assignment(self, sample, *, position="A1"):
        assignment = SampleStorageAssignment.objects.create(
            sample=sample, location=self.source,
            position=position, is_primary=True, rank=1, status="active",
        )
        Sample.objects.filter(pk=sample.pk).update(
            storage_location=f"{self.source.full_path} > {position}"
        )
        return assignment

    def choose(self, *samples):
        return self.client.post(self.path, {
            "action": "choose", "sample_ids": [str(s.pk) for s in samples],
        })

    def preview(self, pairs, destination=None):
        selected = [sample for sample, _ in pairs]
        data = {
            "action": "preview",
            "sample_ids": [str(s.pk) for s in selected],
            "destination_id": str((destination or self.destination).pk),
        }
        data.update({f"position_{s.pk}": position for s, position in pairs})
        return self.client.post(self.path, data)

    def confirm(self, preview, reason="Physical inventory verification"):
        self.assertEqual(preview.status_code, 200, preview.content[:600])
        token = preview.context["bulk_token"]
        self.assertTrue(token)
        return self.client.post(self.path, {
            "action": "confirm", "confirm_token": token, "reason": reason,
        })

    def test_http_method_and_authentication(self):
        self.assertEqual(self.client.get(self.path).status_code, 405)
        self.client.logout()
        response = self.choose(self.a)
        self.assertEqual(response.status_code, 302)

    def test_choose_is_read_only_and_shows_registered_source(self):
        self.initial_assignment(self.c)
        response = self.choose(self.a, self.c)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.a.sample_id)
        self.assertContains(response, self.c.sample_id)
        self.assertContains(response, "Initial registration")
        self.assertContains(response, "Move primary assignment")
        self.assertEqual(StorageMovement.objects.count(), 0)

    def test_two_unassigned_samples_register_and_audit(self):
        preview = self.preview([(self.a, "B5"), (self.b, "B6")])
        self.assertEqual(StorageMovement.objects.count(), 0)
        response = self.confirm(preview)
        self.assertEqual(response.status_code, 302)
        assignments = list(SampleStorageAssignment.objects.filter(
            sample_id__in=[self.a.pk, self.b.pk], status="active",
        ).order_by("position"))
        self.assertEqual([a.position for a in assignments], ["B5", "B6"])
        self.assertTrue(all(a.location_id == self.destination.pk for a in assignments))
        self.assertEqual(StorageMovement.objects.filter(movement_type="registration").count(), 2)
        self.assertEqual(StorageMovementItem.objects.filter(
            sample_id__in=[self.a.pk, self.b.pk],
        ).count(), 2)

    def test_existing_primary_moves_and_secondary_is_unchanged(self):
        original = self.initial_assignment(self.c)
        secondary = SampleStorageAssignment.objects.create(
            sample=self.c, location=self.destination,
            position="Z9", is_primary=False, rank=2, status="active",
        )
        # A primary cannot be moved to a destination already assigned to
        # the same Sample. Choose another authorized Box for this case.
        target = StorageLocation.objects.create(
            name="Bulk Third Box", location_type="box",
            workspace=self.workspace, parent=self.freezer,
        )
        response = self.confirm(self.preview([(self.c, "P03")], destination=target))
        self.assertEqual(response.status_code, 302)
        original.refresh_from_db()
        secondary.refresh_from_db()
        self.assertEqual((original.location_id, original.position), (target.pk, "P03"))
        self.assertEqual((secondary.location_id, secondary.position), (self.destination.pk, "Z9"))
        self.assertEqual(StorageMovement.objects.filter(movement_type="sample_bulk").count(), 1)

    def test_mixed_register_and_move_is_atomic_on_success(self):
        original = self.initial_assignment(self.c)
        response = self.confirm(self.preview([(self.c, "B1"), (self.a, "B2")]))
        self.assertEqual(response.status_code, 302)
        original.refresh_from_db()
        self.assertEqual((original.location_id, original.position), (self.destination.pk, "B1"))
        self.assertTrue(SampleStorageAssignment.objects.filter(
            sample=self.a, location=self.destination, position="B2", status="active",
        ).exists())
        self.assertEqual(StorageMovement.objects.filter(movement_type="sample_bulk").count(), 1)
        self.assertEqual(StorageMovement.objects.filter(movement_type="registration").count(), 1)

    def test_duplicate_positions_rejected_without_changes(self):
        response = self.preview([(self.a, "B1"), (self.b, "b1")])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SampleStorageAssignment.objects.exists())
        self.assertFalse(StorageMovement.objects.exists())

    def test_occupied_slot_rejected_without_changes(self):
        self.initial_assignment(self.c, position="B5")
        other_position = SampleStorageAssignment.objects.create(
            sample=self.b, location=self.destination,
            position="C2", is_primary=True, rank=1, status="active",
        )
        response = self.preview([(self.a, "C2")])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(other_position.location_id, self.destination.pk)
        self.assertFalse(StorageMovement.objects.exists())

    def test_unauthorized_sample_and_destination_denied(self):
        response = self.choose(self.a, self.foreign_sample)
        self.assertEqual(response.status_code, 403)
        response = self.preview([(self.a, "B5")], destination=self.foreign_destination)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StorageMovement.objects.exists())

    def test_rejects_oversized_selection_and_invalid_signature(self):
        response = self.client.post(self.path, {
            "action": "choose", "sample_ids": [str(i) for i in range(1, 52)],
        })
        self.assertEqual(response.status_code, 400)
        response = self.client.post(self.path, {
            "action": "confirm", "confirm_token": "invalid",
            "reason": "Test",
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StorageMovement.objects.exists())

    def test_confirm_rechecks_stale_snapshot(self):
        preview = self.preview([(self.a, "B5")])
        Sample.objects.filter(pk=self.a.pk).update(storage_location="legacy changed")
        response = self.confirm(preview)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SampleStorageAssignment.objects.exists())
        self.assertFalse(StorageMovement.objects.exists())

    def test_mixed_failure_rolls_back_completed_move_and_audit(self):
        original = self.initial_assignment(self.c)
        preview = self.preview([(self.c, "B1"), (self.a, "B2")])
        with patch(
            "core.views.internal.samples.bulk_storage_v8148.register_initial_physical_storage",
            side_effect=ValidationError("Injected registration failure"),
        ) as mock_register:
            response = self.confirm(preview)
            self.assertEqual(response.status_code, 400)
            mock_register.assert_called_once()
        original.refresh_from_db()
        self.assertEqual((original.location_id, original.position), (self.source.pk, "A1"))
        self.assertFalse(SampleStorageAssignment.objects.filter(sample=self.a).exists())
        self.assertFalse(StorageMovement.objects.exists())

    def test_initial_registration_custom_location_host(self):
        custom = StorageLocation.objects.create(
            name="Bulk Custom Registration",
            location_type="other",
            workspace=self.workspace,
            parent=self.freezer,
        )
        response = self.choose(self.a)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            custom.pk,
            [loc.pk for loc in response.context["bulk_destinations"]],
        )
        result = self.confirm(
            self.preview([(self.a, "C7")], destination=custom)
        )
        self.assertEqual(result.status_code, 302)
        self.assertTrue(
            SampleStorageAssignment.objects.filter(
                sample=self.a,
                location=custom,
                position="C7",
                status="active",
            ).exists()
        )

    def test_existing_assignment_move_custom_location_host(self):
        assignment = self.initial_assignment(self.c)
        custom = StorageLocation.objects.create(
            name="Bulk Custom Movement",
            location_type="other",
            workspace=self.workspace,
            parent=self.freezer,
        )
        result = self.confirm(
            self.preview([(self.c, "D8")], destination=custom)
        )
        self.assertEqual(result.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(
            (assignment.location_id, assignment.position),
            (custom.pk, "D8"),
        )
