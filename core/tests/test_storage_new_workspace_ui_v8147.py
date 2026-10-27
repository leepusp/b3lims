from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]
HTML = (
    ROOT / "core/interfaces/internal/storage/index_v814.html"
)
JS = (
    ROOT
    / "core/static/internal/storage/"
    "storage_new_workspace_v8147.js"
)
VIEW = (
    ROOT / "core/views/internal/storage/views.py"
)


class NewStorageUIContractTests(SimpleTestCase):
    def test_creation_uses_existing_server_action(self):
        html = HTML.read_text()
        self.assertIn(
            'value="create_storage_workspace_v8"',
            html,
        )
        self.assertIn(
            "{% url 'storage_workspace' %}",
            html,
        )
        self.assertIn("{% csrf_token %}", html)

    def test_form_uses_existing_service_fields(self):
        html = HTML.read_text()
        for field in (
            'name="workspace_name"',
            'name="workspace_scope"',
            'name="research_group_id"',
        ):
            self.assertIn(field, html)

    def test_new_storage_is_independent_of_existing_locations(self):
        html = HTML.read_text()
        button = html.index('id="b3s-new-storage"')
        conditional = html.index(
            "{% if storage_manageable_workspaces_v8 %}",
            button,
        )
        self.assertLess(button, conditional)

    def test_group_option_respects_server_choices(self):
        html = HTML.read_text()
        self.assertIn(
            "{% if storage_group_choices_v8 %}",
            html,
        )
        self.assertIn(
            "{% for group in storage_group_choices_v8 %}",
            html,
        )

    def test_existing_location_form_is_preserved(self):
        html = HTML.read_text()
        self.assertIn('id="b3s-location-form"', html)
        self.assertIn('id="b3s-create-workspace"', html)
        self.assertIn('id="b3s-create-parent"', html)
        self.assertIn(
            "storage_layout_v8146c3.js",
            html,
        )

    def test_new_modal_has_client_controller(self):
        html = HTML.read_text()
        js = JS.read_text()
        self.assertIn(
            "storage_new_workspace_v8147.js",
            html,
        )
        self.assertIn("dialog.showModal()", js)
        self.assertIn("groupSelect.disabled", js)
        self.assertIn("groupSelect.required", js)

    def test_existing_backend_creation_dispatch_preserved(self):
        view = VIEW.read_text()
        self.assertIn(
            'action == "create_storage_workspace_v8"',
            view,
        )
        self.assertIn(
            "create_storage_workspace_v8(",
            view,
        )
