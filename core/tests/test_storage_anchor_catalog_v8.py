from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import StorageLocation, StorageWorkspace
from core.services.storage_anchor_catalog_v8 import (
    build_storage_anchor_catalog,
)


class StorageAnchorCatalogV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="anchor-catalog-v8",
        )

        cls.freezer = StorageLocation.objects.create(
            name="Freezer Regina",
            location_type="freezer",
        )
        cls.box = StorageLocation.objects.create(
            name="Caixa 1.1",
            location_type="box",
            parent=cls.freezer,
        )

        cls.refrigerator = StorageLocation.objects.create(
            name="Refrigerator A",
            location_type="other",
        )
        cls.shelf = StorageLocation.objects.create(
            name="Shelf 2",
            location_type="shelf",
            parent=cls.refrigerator,
        )
        cls.rack = StorageLocation.objects.create(
            name="Rack 4",
            location_type="rack",
            parent=cls.shelf,
        )


        cls.workspace = StorageWorkspace.objects.create(
            name="Catalog Test Storage",
            scope="personal",
            owner=cls.user,
        )

        StorageLocation.objects.filter(
            pk__in=[
                cls.freezer.pk,
                cls.box.pk,
                cls.refrigerator.pk,
                cls.shelf.pk,
                cls.rack.pk,
            ]
        ).update(workspace=cls.workspace)

    def test_nested_generic_hierarchies(self):
        rows = build_storage_anchor_catalog(user=self.user)
        by_id = {row["id"]: row for row in rows}

        self.assertEqual(
            by_id[self.box.pk]["full_path"],
            "Freezer Regina > Caixa 1.1",
        )
        self.assertEqual(
            by_id[self.rack.pk]["full_path"],
            "Refrigerator A > Shelf 2 > Rack 4",
        )
        self.assertEqual(
            by_id[self.rack.pk]["parent_id"],
            self.shelf.pk,
        )

    def test_inactive_ancestor_excludes_descendants(self):
        self.refrigerator.is_active = False
        self.refrigerator.save(
            update_fields=["is_active"]
        )

        ids = {
            row["id"]
            for row in build_storage_anchor_catalog(user=self.user)
        }

        self.assertNotIn(self.refrigerator.pk, ids)
        self.assertNotIn(self.shelf.pk, ids)
        self.assertNotIn(self.rack.pk, ids)

    def test_no_physical_inventory_mutation(self):
        before = list(
            StorageLocation.objects
            .order_by("pk")
            .values_list(
                "pk", "parent_id", "name",
                "location_type", "is_active",
            )
        )

        build_storage_anchor_catalog(user=self.user)

        after = list(
            StorageLocation.objects
            .order_by("pk")
            .values_list(
                "pk", "parent_id", "name",
                "location_type", "is_active",
            )
        )

        self.assertEqual(before, after)

    def test_endpoint_requires_authentication(self):
        response = self.client.get(
            reverse("storage_anchor_catalog_v8")
        )
        self.assertEqual(response.status_code, 302)

    def test_endpoint_returns_registered_anchors(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("storage_anchor_catalog_v8")
        )

        self.assertEqual(response.status_code, 200)

        payload = response.json()

        self.assertTrue(payload["read_only"])

        by_id = {
            row["id"]: row
            for row in payload["anchors"]
        }

        self.assertEqual(
            by_id[self.box.pk]["full_path"],
            "Freezer Regina > Caixa 1.1",
        )
        self.assertEqual(
            by_id[self.rack.pk]["location_type"],
            "rack",
        )

        self.assertNotIn("available_slots", payload)
        self.assertNotIn("free_positions", payload)

    def test_endpoint_rejects_post(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("storage_anchor_catalog_v8")
        )

        self.assertEqual(response.status_code, 405)
