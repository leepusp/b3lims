"""Storage organization and dimensions, V8.14.6C3."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.storage import (
    StorageLocation,
    StorageLocationLayoutV8146C3,
    StorageWorkspace,
)


class StorageLayoutC3Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(
            username="storage-c3-owner",
        )
        cls.workspace = StorageWorkspace.objects.create(
            name="C3 test workspace",
            scope="personal",
            owner=user,
        )
        cls.location = StorageLocation.objects.create(
            name="Caixa experimental",
            location_type="other",
            workspace=cls.workspace,
        )

    def make_layout(self, organization, rows, columns):
        return StorageLocationLayoutV8146C3(
            location=self.location,
            organization=organization,
            rows=rows,
            columns=columns,
        )

    def test_existing_location_requires_no_grid_configuration(self):
        self.assertFalse(
            StorageLocationLayoutV8146C3.objects.filter(
                location=self.location
            ).exists()
        )

    def test_grid_capacity_9_by_9(self):
        layout = self.make_layout("grid", 9, 9)
        layout.full_clean()
        self.assertEqual(layout.capacity, 81)

    def test_grid_capacity_8_by_12(self):
        layout = self.make_layout("grid", 8, 12)
        layout.full_clean()
        self.assertEqual(layout.capacity, 96)

    def test_free_layout_has_no_finite_capacity(self):
        layout = self.make_layout("free", 0, 0)
        layout.full_clean()
        self.assertIsNone(layout.capacity)

    def test_incomplete_grid_is_rejected(self):
        for dimensions in ((0, 9), (9, 0), (0, 0)):
            with self.subTest(dimensions=dimensions):
                layout = self.make_layout(
                    "grid", *dimensions
                )
                with self.assertRaises(ValidationError):
                    layout.full_clean()

    def test_oversized_grid_is_rejected(self):
        for dimensions in ((27, 9), (9, 25)):
            with self.subTest(dimensions=dimensions):
                layout = self.make_layout(
                    "grid", *dimensions
                )
                with self.assertRaises(ValidationError):
                    layout.full_clean()

    def test_free_layout_rejects_dimensions(self):
        layout = self.make_layout("free", 9, 9)
        with self.assertRaises(ValidationError):
            layout.full_clean()

    def test_configuration_persists_without_new_positions(self):
        layout = self.make_layout("grid", 9, 9)
        layout.type_label = "Caixa"
        layout.temperature_label = "-80 C"
        layout.full_clean()
        layout.save()

        loaded = StorageLocationLayoutV8146C3.objects.get(
            location=self.location
        )

        self.assertEqual(loaded.capacity, 81)
        self.assertEqual(loaded.type_label, "Caixa")
        self.assertEqual(loaded.temperature_label, "-80 C")
        self.assertEqual(
            self.location.sample_assignments.count(),
            0,
        )
