from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.storage import StorageLocation, StorageLocationLayoutV8146C3, StorageWorkspace
from core.services.storage_anchor_catalog_v8 import build_storage_anchor_catalog


class AutoWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("auto-ws", password="x")
        self.client.force_login(self.user)
        self.url = reverse("storage_path_register_v8146")

    def register(self, path, **extra):
        return self.client.post(self.url, {"workspace_id": "", "path": path, **extra})

    def test_first_level_becomes_the_workspace_and_last_level_gets_its_layout(self):
        response = self.register("Lab A > Freezer 1 > Box 2", organization="grid", rows="8", columns="12")
        data = response.json()

        self.assertEqual(response.status_code, 201, data)
        self.assertEqual(data["workspace"], {"id": StorageWorkspace.objects.get().pk, "name": "Lab A", "created": True})
        self.assertEqual(data["anchor"]["full_path"], "Freezer 1 > Box 2")

        workspace = StorageWorkspace.objects.get()

        self.assertEqual((workspace.scope, workspace.owner), ("personal", self.user))

        layout = StorageLocationLayoutV8146C3.objects.get(location__name="Box 2")

        self.assertEqual((layout.organization, layout.rows, layout.columns), ("grid", 8, 12))
        self.assertFalse(StorageLocationLayoutV8146C3.objects.filter(location__name="Freezer 1").exists())

    def test_second_registration_reuses_the_workspace_and_levels(self):
        self.register("Lab A > Freezer 1 > Box 2")
        again = self.register("lab a > freezer 1 > Box 3", organization="slots", slot_label=["Door 1", "Door 2"], slot_direction="row").json()

        self.assertEqual(StorageWorkspace.objects.count(), 1)
        self.assertFalse(again["workspace"]["created"])
        self.assertEqual((again["created_count"], again["reused_count"]), (1, 1))
        self.assertEqual(StorageLocationLayoutV8146C3.objects.get(location__name="Box 3").slot_labels, ["Door 1", "Door 2"])

    def test_a_single_level_without_a_workspace_is_refused(self):
        response = self.register("Lab A")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StorageWorkspace.objects.exists())

    def test_invalid_layout_creates_nothing(self):
        response = self.register("Lab A > Freezer 1", organization="grid", rows="99", columns="3")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StorageWorkspace.objects.exists())
        self.assertFalse(StorageLocation.objects.exists())

    def test_levels_are_appended_in_order_and_catalog_names_the_workspace(self):
        self.register("Lab A > Freezer 1")
        self.register("Lab A > Freezer 2")

        ranks = list(StorageLocation.objects.filter(parent=None).order_by("name").values_list("rank", flat=True))
        catalog = build_storage_anchor_catalog(user=self.user)

        self.assertEqual(ranks, [1, 2])
        self.assertEqual({a["workspace_id"] for a in catalog}, {StorageWorkspace.objects.get().pk})
