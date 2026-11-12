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


class StoragePageCleanupTests(TestCase):
    def test_removed_panels_are_not_on_the_page(self):
        user = get_user_model().objects.create_user("cleanup-user", password="x")
        self.client.force_login(user)
        html = self.client.get(reverse("storage_workspace")).content.decode()

        self.assertNotIn("Historical registrations", html)
        self.assertNotIn("Move Container", html)
        self.assertNotIn(">Transfers<", html)


class StorageChildPreviewTests(TestCase):
    def test_layout_preview_container_and_script_are_on_the_sample_form(self):
        user = get_user_model().objects.create_user("preview-user", password="x")
        self.client.force_login(user)
        html = self.client.get(reverse("sample_add")).content.decode()

        self.assertIn('id="storageChildPreviewV8146"', html)
        self.assertIn("20261112-preview2", html)

    def test_sample_form_is_a_single_panel_in_order(self):
        user = get_user_model().objects.create_user("panel-user", password="x")
        self.client.force_login(user)
        html = self.client.get(reverse("sample_add")).content.decode()

        order = [html.index(x) for x in (
            'id="storageChildWorkspaceV8146"', 'id="storageInputVisual"',
            'id="storageChildLayoutV8146"', 'id="storageChildCreateV8146"', 'id="storagePositionPanelV8"',
        )]
        self.assertEqual(order, sorted(order))
        self.assertEqual(html.count('data-b3-storage-child-v8146'), 1)
