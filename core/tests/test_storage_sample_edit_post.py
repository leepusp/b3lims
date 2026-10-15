from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_container_movements import (
    move_storage_container,
)
from core.services.storage_locations import (
    _sync_legacy_storage_levels,
    get_all_storage_paths,
)


class SampleStorageEditPostTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="a2-post-owner",
            is_staff=True,
        )

        cls.room = StorageLocation.objects.create(
            name="Sala A",
            location_type="room",
        )
        cls.freezer_a = StorageLocation.objects.create(
            name="Freezer A",
            parent=cls.room,
            location_type="freezer",
        )
        cls.freezer_b = StorageLocation.objects.create(
            name="Freezer B",
            parent=cls.room,
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Caixa Y",
            parent=cls.freezer_a,
            location_type="box",
        )
        cls.shelf = StorageLocation.objects.create(
            name="Prateleira",
            parent=cls.freezer_a,
            location_type="shelf",
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="A2 Sample Edit Workspace",
            scope="personal",
            owner=cls.user,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.room.pk,
                cls.freezer_a.pk,
                cls.freezer_b.pk,
                cls.box.pk,
                cls.shelf.pk,
            ]
        ).update(workspace=cls.workspace)

        cls.sample = Sample.objects.create(
            sample_id="A2-POST-001",
            sample_type="Other",
            organism_name="Sample A2",
            owner=cls.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=cls.box.full_path,
        )

        SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.box,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )
        SampleStorageAssignment.objects.create(
            sample=cls.sample,
            location=cls.shelf,
            rank=2,
            is_primary=False,
            position="S01",
            status="active",
        )

        _sync_legacy_storage_levels(
            cls.sample,
            cls.box.full_path_parts,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("sample_edit", args=[self.sample.pk])

    def form_payload(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        data = {}

        for form in (
            response.context["form"],
            response.context["origin_form"],
        ):
            for name, field in form.fields.items():
                if isinstance(field, forms.FileField):
                    continue

                value = form[name].value()
                key = form.add_prefix(name)

                if isinstance(field, forms.BooleanField):
                    if value:
                        data[key] = "on"
                elif isinstance(value, (list, tuple)):
                    data[key] = [
                        str(item) for item in value
                    ]
                elif value is not None:
                    data[key] = str(value)

        data["storage_initial_paths"] = (
            response.context["form"]
            .initial.get("storage_location", "")
        )
        data["storage_edit_intent"] = "0"

        return data

    def assignment_snapshot(self):
        return list(
            SampleStorageAssignment.objects
            .filter(sample=self.sample)
            .order_by("pk")
            .values_list(
                "pk",
                "location_id",
                "rank",
                "is_primary",
                "position",
                "status",
            )
        )

    def assert_saved(self, response):
        if response.status_code != 302:
            context = response.context
            errors = (
                context["form"].errors
                if context is not None
                else "No form context"
            )
            origin_errors = (
                context["origin_form"].errors
                if context is not None
                else "No origin form context"
            )
            self.fail(
                f"Expected successful POST, got "
                f"{response.status_code}; "
                f"form={errors}; origin={origin_errors}"
            )

    def move_box(self):
        return move_storage_container(
            container=self.box,
            destination=self.freezer_b,
            actor=self.user,
            expected_parent_id=self.freezer_a.pk,
            reason="A2 stale form regression test",
        )

    def test_metadata_save_preserves_both_assignments(self):
        before = self.assignment_snapshot()
        data = self.form_payload()

        data["scientific_notes"] = (
            "Metadata edited without moving the Sample."
        )

        self.assert_saved(
            self.client.post(self.url, data)
        )

        self.assertEqual(
            self.assignment_snapshot(),
            before,
        )
        self.assertEqual(
            len(get_all_storage_paths(self.sample)),
            2,
        )

    def test_stale_metadata_form_preserves_container_move(self):
        data = self.form_payload()

        self.move_box()

        after_movement = self.assignment_snapshot()

        data["scientific_notes"] = (
            "Edited after the container was moved."
        )

        self.assert_saved(
            self.client.post(self.url, data)
        )

        self.sample.refresh_from_db()

        self.assertEqual(
            self.assignment_snapshot(),
            after_movement,
        )
        self.assertEqual(
            self.sample.storage_location,
            "Sala A > Freezer B > Caixa Y > P01",
        )
        self.assertEqual(
            get_all_storage_paths(self.sample)[0],
            "Sala A > Freezer B > Caixa Y",
        )

    def test_stale_explicit_move_is_rejected(self):
        data = self.form_payload()

        self.move_box()

        after_movement = self.assignment_snapshot()

        data["storage_edit_intent"] = "1"
        data["storage_location"] = (
            "Sala A > Freezer A > Prateleira"
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "storage_location",
            response.context["form"].errors,
        )
        self.assertEqual(
            self.assignment_snapshot(),
            after_movement,
        )

        self.sample.refresh_from_db()
        self.assertEqual(
            self.sample.storage_location,
            "Sala A > Freezer B > Caixa Y > P01",
        )

    def test_hidden_path_change_without_intent_is_ignored(self):
        before = self.assignment_snapshot()
        data = self.form_payload()

        data["storage_edit_intent"] = "0"
        data["storage_location"] = (
            "Sala A > Freezer B"
        )

        self.assert_saved(
            self.client.post(self.url, data)
        )

        self.assertEqual(
            self.assignment_snapshot(),
            before,
        )

    def test_explicit_move_preserves_secondary_assignment(self):
        """
        Editing the primary location must not destroy an
        unchanged secondary assignment or its physical position.
        """
        data = self.form_payload()

        secondary = SampleStorageAssignment.objects.get(
            sample=self.sample,
            location=self.shelf,
            status="active",
        )

        previous_secondary = {
            "pk": secondary.pk,
            "position": secondary.position,
            "rank": secondary.rank,
            "is_primary": secondary.is_primary,
            "container_type": secondary.container_type,
            "quantity": secondary.quantity,
            "quantity_unit": secondary.quantity_unit,
            "notes": secondary.notes,
        }

        data["storage_edit_intent"] = "1"
        data["storage_location"] = "; ".join([
            self.freezer_b.full_path,
            self.shelf.full_path,
        ])

        response = self.client.post(self.url, data)
        self.assert_saved(response)

        # Secondary assignment must retain its identity.
        secondary.refresh_from_db()

        current_secondary = {
            "pk": secondary.pk,
            "position": secondary.position,
            "rank": secondary.rank,
            "is_primary": secondary.is_primary,
            "container_type": secondary.container_type,
            "quantity": secondary.quantity,
            "quantity_unit": secondary.quantity_unit,
            "notes": secondary.notes,
        }

        self.assertEqual(
            current_secondary,
            previous_secondary,
        )

        self.assertEqual(
            get_all_storage_paths(self.sample),
            [
                self.freezer_b.full_path,
                self.shelf.full_path,
            ],
        )


    def test_storage_failure_rolls_back_metadata(self):
        """A failed storage edit must roll back earlier metadata writes."""
        from unittest.mock import patch
        from django.core.exceptions import ValidationError

        data = self.form_payload()
        self.sample.refresh_from_db()

        original_notes = self.sample.scientific_notes
        original_assignments = self.assignment_snapshot()

        data["scientific_notes"] = (
            "E1C metadata that must be rolled back"
        )
        data["storage_edit_intent"] = "1"
        data["storage_location"] = (
            f"{self.freezer_b.full_path}; {self.shelf.full_path}"
        )

        with patch(
            "core.services.storage_assignment_reconcile."
            "reconcile_sample_storage_from_text",
            side_effect=ValidationError(
                "E1C injected reconciliation failure"
            ),
        ):
            with self.assertRaisesRegex(
                ValidationError,
                "E1C injected reconciliation failure",
            ):
                self.client.post(self.url, data)

        self.sample.refresh_from_db()

        self.assertEqual(
            self.sample.scientific_notes,
            original_notes,
            "Metadata must be rolled back if storage reconciliation fails.",
        )
        self.assertEqual(
            self.assignment_snapshot(),
            original_assignments,
        )


    def test_metadata_edit_does_not_create_storage_audit(self):
        """Metadata-only edits must not register physical movement."""
        from core.models.samples.storage import StorageMovement

        data = self.form_payload()
        data["scientific_notes"] = "Metadata-only E2C update."
        data["storage_edit_intent"] = "0"

        self.assert_saved(self.client.post(self.url, data))
        self.assertFalse(StorageMovement.objects.exists())

    def test_explicit_storage_path_edit_creates_audit(self):
        """An explicit path change must retain an audit snapshot."""
        from core.models.samples.storage import StorageMovement

        primary = SampleStorageAssignment.objects.get(
            sample=self.sample,
            rank=1,
        )
        original_id = primary.pk

        data = self.form_payload()
        data["storage_edit_intent"] = "1"
        data["storage_location"] = (
            f"{self.freezer_b.full_path}; "
            f"{self.shelf.full_path}"
        )

        self.assert_saved(self.client.post(self.url, data))

        primary.refresh_from_db()
        self.assertEqual(primary.pk, original_id)
        self.assertEqual(primary.location_id, self.freezer_b.pk)

        movement = StorageMovement.objects.get(
            movement_type="sample",
        )
        self.assertEqual(movement.performed_by_id, self.user.pk)
        self.assertTrue(movement.reason.strip())

        item = movement.items.get(
            assignment_id_snapshot=original_id,
        )
        self.assertEqual(item.path_before, self.box.full_path)
        self.assertEqual(item.path_after, self.freezer_b.full_path)
        self.assertEqual(item.position_before, "P01")
        self.assertEqual(item.position_after, "")

    def test_secondary_removal_creates_audit_snapshot(self):
        """Removing a secondary path must retain its historical slot."""
        from core.models.samples.storage import StorageMovement

        secondary = SampleStorageAssignment.objects.get(
            sample=self.sample,
            rank=2,
        )
        original_id = secondary.pk

        data = self.form_payload()
        data["storage_edit_intent"] = "1"
        data["storage_location"] = self.box.full_path

        self.assert_saved(self.client.post(self.url, data))

        movement = StorageMovement.objects.get(
            movement_type="sample",
        )
        self.assertEqual(movement.performed_by_id, self.user.pk)

        item = movement.items.get(
            assignment_id_snapshot=original_id,
        )
        self.assertEqual(item.path_before, self.shelf.full_path)
        self.assertEqual(item.path_after, "")
        self.assertEqual(item.position_before, "S01")
        self.assertEqual(item.position_after, "")


    def test_protected_secondary_removal_rolls_back_and_shows_message(self):
        """A rejected physical removal must not persist any edit."""
        from decimal import Decimal
        from django.contrib.messages import get_messages
        from core.models.samples.storage import StorageMovement

        secondary = SampleStorageAssignment.objects.get(
            sample=self.sample,
            rank=2,
        )

        secondary.container_type = "Cryovial"
        secondary.quantity = Decimal("2.500")
        secondary.quantity_unit = "mL"
        secondary.notes = "Preserve original physical inventory."
        secondary.save(
            update_fields=[
                "container_type",
                "quantity",
                "quantity_unit",
                "notes",
            ]
        )

        self.sample.refresh_from_db()
        original_notes = self.sample.scientific_notes

        data = self.form_payload()
        data["storage_edit_intent"] = "1"
        data["storage_location"] = self.box.full_path
        data["scientific_notes"] = "This edit must roll back."

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)

        feedback = [
            str(message)
            for message in get_messages(response.wsgi_request)
        ]

        self.assertTrue(
            any(
                "physical metadata cannot be removed" in message
                for message in feedback
            ),
            feedback,
        )

        self.sample.refresh_from_db()
        secondary.refresh_from_db()

        self.assertEqual(self.sample.scientific_notes, original_notes)
        self.assertEqual(secondary.location_id, self.shelf.pk)
        self.assertEqual(secondary.position, "S01")
        self.assertEqual(secondary.container_type, "Cryovial")
        self.assertEqual(secondary.quantity, Decimal("2.500"))
        self.assertEqual(secondary.quantity_unit, "mL")
        self.assertEqual(
            secondary.notes,
            "Preserve original physical inventory.",
        )
        self.assertFalse(StorageMovement.objects.exists())
