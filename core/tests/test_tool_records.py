import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.tool_record import ToolRecord, tool_record_upload_to
from core.services import lab_tools_storage as storage

ROOT = Path(__file__).resolve().parents[2]


class _Owner:
    def get_username(self):
        return "analyst"


class _Rec:
    pk = 7
    owner_id = 1
    tool = "gel"
    owner = _Owner()


class ToolRecordStorageLayoutTests(SimpleTestCase):
    def test_upload_path_is_a_folder_named_after_the_tool(self):
        name = tool_record_upload_to(_Rec(), "My gel (1).png")

        self.assertRegex(name, r"^users/analyst/tools/gel/7/[0-9a-f]{32}_My_gel_1_.png$")

    def test_tools_area_is_allowed_and_nothing_else_was_opened(self):
        self.assertIn("tools", storage.ALLOWED_AREAS)
        self.assertEqual(
            storage.ALLOWED_AREAS,
            {"eln", "exports", "jupyter", "molecular", "tmp", "tools"},
        )

    def test_runner_only_manages_known_tool_folders(self):
        source = (ROOT / "deploy/sbin/biobank-user-storage").read_text(encoding="utf-8")

        self.assertIn("tools/(gel|assembly|chemical)/[0-9]+/[A-Za-z0-9_.-]+", source)
        self.assertIn('"$LAB_ROOT/tools"', source)


class ToolRecordBrokerPolicyTests(SimpleTestCase):
    """The app runs as `biobank` and reaches storage through the broker, so the
    broker must know the per-tool folders too (and nothing broader)."""

    @classmethod
    def broker(cls):
        import importlib.machinery
        import importlib.util

        path = str(ROOT / "deploy/sbin/biobank-user-storage-broker")
        loader = importlib.machinery.SourceFileLoader("storage_broker_tools_test", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)

        return module

    def test_directories(self):
        broker = self.broker()

        for ok in ("tools/gel", "tools/gel/2", "tools/assembly/10", "tools/chemical/3"):
            self.assertTrue(broker.LAB_DIRECTORY_RE.fullmatch(ok), ok)

        for bad in ("tools", "tools/other/2", "tools/gel/2/x", "tools/gel/x"):
            self.assertFalse(broker.LAB_DIRECTORY_RE.fullmatch(bad), bad)

    def test_files(self):
        broker = self.broker()

        self.assertTrue(broker.LAB_FILE_RE.fullmatch("tools/gel/2/abc_photo.png"))

        for bad in ("tools/gel/2/sub/x.png", "tools/gel/x.png", "tools/other/2/x.png"):
            self.assertFalse(broker.LAB_FILE_RE.fullmatch(bad), bad)

    def test_layout_creates_the_tools_folder(self):
        self.assertIn("biobank/lab_tools/tools", self.broker().BASE_LAYOUT)


@override_settings(FORCE_SCRIPT_NAME=None)
class ToolRecordViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="tool-owner", password="pw")
        self.other = user_model.objects.create_user(username="tool-other", password="pw")

    def make(self, tool="gel"):
        return ToolRecord.objects.create(tool=tool, name="Run 1", owner=self.owner, data={})

    def test_create_from_the_dashboard_form(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("tool_record_create"), {"tool": "assembly", "name": "pUC build"})
        record = ToolRecord.objects.get(name="pUC build")

        self.assertRedirects(response, reverse("tool_record_detail", args=[record.id]), fetch_redirect_response=False)
        self.assertEqual(record.tool, "assembly")
        self.assertEqual(record.owner, self.owner)

    def test_create_rejects_unknown_tool_and_blank_name(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("tool_record_create"), {"tool": "nope", "name": "x"})
        self.client.post(reverse("tool_record_create"), {"tool": "gel", "name": "  "})

        self.assertEqual(ToolRecord.objects.count(), 0)

    def test_every_type_renders_its_own_page_with_all_windows(self):
        self.client.force_login(self.owner)

        for tool in ("gel", "assembly", "chemical"):
            record = self.make(tool)
            response = self.client.get(reverse("tool_record_detail", args=[record.id]))

            self.assertContains(response, f'data-tool="{tool}"')
            for key in ("gel", "assembly", "chemical", "notes"):
                self.assertContains(response, f'data-tw-toggle="{key}"')

    def test_page_has_layout_controls_and_a_resizable_side_column(self):
        record = self.make("gel")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("tool_record_detail", args=[record.id]))

        for mode in ("split", "stack", "tabs"):
            self.assertContains(response, f'data-tw-layout="{mode}"')

        self.assertContains(response, 'id="tw-divider"')
        self.assertContains(response, 'id="tw-side"')
        self.assertContains(response, 'id="tw-tabs"')

    def test_sequence_windows_are_available_in_every_tool(self):
        self.client.force_login(self.owner)

        for tool in ("gel", "assembly", "chemical"):
            record = self.make(tool)
            response = self.client.get(reverse("tool_record_detail", args=[record.id]))

            for key in ("sequence", "digest", "primers", "cloning"):
                self.assertContains(response, f'data-tw-toggle="{key}"')

            for element in ("tw-sequence", "mw-digest", "mw-primers", "mw-cloning"):
                self.assertContains(response, f'id="{element}"')

            self.assertContains(response, 'id="molecular-workspace"')
            self.assertContains(response, "tool_sequence_window.js")

    def test_only_the_owner_opens_a_record(self):
        record = self.make()
        url = reverse("tool_record_detail", args=[record.id])

        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("tool_record_state_api", args=[record.id]), "{}", content_type="application/json").status_code, 404)
        self.assertEqual(self.client.post(reverse("tool_record_delete_api", args=[record.id])).status_code, 404)

    def test_state_is_saved_and_validated(self):
        record = self.make()
        url = reverse("tool_record_state_api", args=[record.id])
        self.client.force_login(self.owner)

        ok = self.client.post(url, json.dumps({"data": {"windows": ["gel"], "gel": {"lanes": []}}, "name": "Renamed"}), content_type="application/json")
        record.refresh_from_db()

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(record.name, "Renamed")
        self.assertEqual(record.data["windows"], ["gel"])
        self.assertEqual(self.client.post(url, "[]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, json.dumps({"data": []}), content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, json.dumps({"name": " "}), content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_file_type_is_checked_per_tool(self):
        record = self.make("gel")
        url = reverse("tool_record_file_api", args=[record.id])
        self.client.force_login(self.owner)

        response = self.client.post(url, {"file": SimpleUploadedFile("evil.exe", b"MZ")})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_file_is_stored_through_the_protected_storage(self):
        record = self.make("gel")
        url = reverse("tool_record_file_api", args=[record.id])
        self.client.force_login(self.owner)
        saved = []

        def fake_save(self_storage, name, content):
            saved.append(name)
            return name

        with patch.object(storage.UserHomeLabToolsStorage, "_save", fake_save), patch.object(
            storage.UserHomeLabToolsStorage, "exists", lambda self_storage, name: False
        ):
            response = self.client.post(url, {"file": SimpleUploadedFile("gel.png", b"\x89PNG")})

        record.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(record.original_filename, "gel.png")
        self.assertRegex(saved[0], rf"^users/tool-owner/tools/gel/{record.id}/[0-9a-f]{{32}}_gel.png$")

    def test_create_can_start_from_a_dropped_file(self):
        self.client.force_login(self.owner)
        saved = []

        def fake_save(self_storage, name, content):
            saved.append(name)
            return name

        with patch.object(storage.UserHomeLabToolsStorage, "_save", fake_save), patch.object(
            storage.UserHomeLabToolsStorage, "exists", lambda self_storage, name: False
        ):
            response = self.client.post(
                reverse("tool_record_create"),
                {"tool": "gel", "name": "dropped", "file": SimpleUploadedFile("dropped.png", b"\x89PNG")},
            )

        record = ToolRecord.objects.get(name="dropped")

        self.assertRedirects(response, reverse("tool_record_detail", args=[record.id]), fetch_redirect_response=False)
        self.assertEqual(record.original_filename, "dropped.png")
        self.assertRegex(saved[0], rf"/tools/gel/{record.id}/")

    def test_create_with_a_file_of_the_wrong_kind_creates_nothing(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("tool_record_create"),
            {"tool": "gel", "name": "bad", "file": SimpleUploadedFile("x.mol", b"M  END")},
        )

        self.assertFalse(ToolRecord.objects.filter(name="bad").exists())

    def test_storage_failure_is_reported_with_its_reason(self):
        record = self.make("gel")
        url = reverse("tool_record_file_api", args=[record.id])
        self.client.force_login(self.owner)

        def boom(self_storage, name, content):
            raise storage.LabToolsStorageError("runner said no")

        with patch.object(storage.UserHomeLabToolsStorage, "_save", boom), patch.object(
            storage.UserHomeLabToolsStorage, "exists", lambda self_storage, name: False
        ):
            response = self.client.post(url, {"file": SimpleUploadedFile("gel.png", b"\x89PNG")})

        record.refresh_from_db()

        self.assertEqual(response.status_code, 500)
        self.assertIn("runner said no", response.json()["message"])
        self.assertFalse(record.file)

    def test_delete(self):
        record = self.make()
        self.client.force_login(self.owner)
        response = self.client.post(reverse("tool_record_delete_api", args=[record.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ToolRecord.objects.filter(pk=record.id).exists())


@override_settings(FORCE_SCRIPT_NAME=None)
class RegistryDashboardToolsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dash-user", password="pw")
        self.client.force_login(self.user)

    def test_dashboard_offers_the_tools_as_types_and_one_file_entry(self):
        response = self.client.get(reverse("molecular_registry_index"))

        for value in ("gel", "assembly", "chemical"):
            self.assertContains(response, f'value="tool:{value}"')
            self.assertContains(response, f"?type={value}")

        self.assertContains(response, "data-tool-create-url")
        # One file entry point, inside the New record form.
        content = response.content.decode()
        form_start = content.index('id="molecular-registry-create-form"')
        self.assertGreater(content.index('id="mr-home-drop"'), form_start)
        self.assertEqual(content.count('id="mr-home-drop"'), 1)
        self.assertContains(response, "New record")

    def test_tool_type_filter_lists_only_that_tool(self):
        ToolRecord.objects.create(tool="gel", name="Gel A", owner=self.user)
        ToolRecord.objects.create(tool="chemical", name="Aspirin", owner=self.user)
        response = self.client.get(reverse("molecular_registry_index") + "?type=gel")

        self.assertContains(response, "Gel A")
        self.assertNotContains(response, "Aspirin")


class ChemicalWindowWiringTests(TestCase):
    def test_chemical_pane_knows_the_stock_list_url(self):
        user = get_user_model().objects.create_user("chemwire", password="x")
        record = ToolRecord.objects.create(tool="chemical", name="Aspirin", owner=user)
        self.client.force_login(user)

        html = self.client.get(f"/internal/lab-tools/tools/{record.pk}/").content.decode()

        self.assertIn('id="tw-chemical"', html)
        self.assertIn('data-stock-url="/chemicals/"', html)
