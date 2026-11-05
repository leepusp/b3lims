"""Editing the drawing of an existing location."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageLocationLayoutV8146C3,
    StorageWorkspace,
)
from core.services.storage_layout_edit import update_location_layout


def sample(identifier, owner):
    return Sample.objects.create(
        sample_id=identifier, sample_type="Other", organism_name=identifier,
        owner=owner, status="available", is_active=True, is_public=False,
    )


class LayoutEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="b3-edit-owner")
        cls.other = User.objects.create_user(username="b3-edit-other")
        cls.ws = StorageWorkspace.objects.create(
            name="Edit ws", scope="personal", owner=cls.owner
        )
        cls.cabinet = StorageLocation.objects.create(
            name="Cab", location_type="other", workspace=cls.ws
        )
        StorageLocationLayoutV8146C3.objects.create(
            location=cls.cabinet, organization="slots",
            slot_labels=["Door 1", "Door 2"], slot_direction="column",
        )
        cls.box = StorageLocation.objects.create(
            name="Box", location_type="box", workspace=cls.ws
        )
        StorageLocationLayoutV8146C3.objects.create(
            location=cls.box, organization="grid", rows=3, columns=3,
        )
        cls.s1 = sample("EDIT-1", cls.owner)
        cls.s2 = sample("EDIT-2", cls.owner)
        SampleStorageAssignment.objects.create(
            sample=cls.s1, location=cls.cabinet, position="Door 2",
            is_primary=True, rank=1, status="active",
        )
        SampleStorageAssignment.objects.create(
            sample=cls.s2, location=cls.box, position="C3",
            is_primary=True, rank=1, status="active",
        )

    def call(self, location, **kw):
        return update_location_layout(
            actor=self.owner, location_id=location.pk, **kw
        )

    def test_add_a_door_keeps_samples(self):
        self.call(
            self.cabinet, organization="slots",
            slot_labels=["Door 1", "Door 2", "Door 3"],
            slot_old=["Door 1", "Door 2", ""],
        )
        layout = StorageLocationLayoutV8146C3.objects.get(location=self.cabinet)
        self.assertEqual(layout.slot_labels, ["Door 1", "Door 2", "Door 3"])

    def test_rename_carries_samples(self):
        self.call(
            self.cabinet, organization="slots",
            slot_labels=["Top", "Door 2"], slot_old=["Door 1", "Door 2"],
        )
        self.call(
            self.cabinet, organization="slots",
            slot_labels=["Top", "Bottom"], slot_old=["Top", "Door 2"],
        )
        item = SampleStorageAssignment.objects.get(sample=self.s1)
        self.assertEqual(item.position, "Bottom")

    def test_removing_an_occupied_door_is_refused_and_rolled_back(self):
        with self.assertRaises(ValidationError):
            self.call(
                self.cabinet, organization="slots",
                slot_labels=["Door 1"], slot_old=["Door 1"],
            )
        layout = StorageLocationLayoutV8146C3.objects.get(location=self.cabinet)
        self.assertEqual(layout.slot_labels, ["Door 1", "Door 2"])

    def test_shrinking_a_grid_under_a_sample_is_refused(self):
        with self.assertRaises(ValidationError):
            self.call(self.box, organization="grid", rows=2, columns=3)
        self.call(self.box, organization="grid", rows=5, columns=6)
        layout = StorageLocationLayoutV8146C3.objects.get(location=self.box)
        self.assertEqual((layout.rows, layout.columns), (5, 6))

    def test_swap_names_is_refused(self):
        with self.assertRaises(ValidationError):
            self.call(
                self.cabinet, organization="slots",
                slot_labels=["Door 2", "Door 1"], slot_old=["Door 1", "Door 2"],
            )

    def test_free_location_can_get_a_drawing(self):
        room = StorageLocation.objects.create(
            name="Room", location_type="room", workspace=self.ws
        )
        self.call(room, organization="grid", rows=2, columns=2)
        self.assertEqual(
            StorageLocationLayoutV8146C3.objects.get(location=room).capacity, 4
        )

    def test_other_user_cannot_edit(self):
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            update_location_layout(
                actor=self.other, location_id=self.box.pk,
                organization="grid", rows=9, columns=9,
            )

    def test_http_endpoint(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("storage_location_layout_update"),
            {"location_id": self.box.pk, "organization": "grid",
             "rows": "4", "columns": "4"},
        )
        self.assertEqual(response.status_code, 302)
        layout = StorageLocationLayoutV8146C3.objects.get(location=self.box)
        self.assertEqual(layout.rows, 4)
        self.client.logout()
        self.assertEqual(
            self.client.post(
                reverse("storage_location_layout_update"), {}
            ).status_code,
            302,
        )
