from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from core.services.extension_panels import (
    ExtensionPanel,
    panels_for,
    register_panel,
    unregister_panel,
)


SLOT = "test.slot"


class ExtensionPanelRegistryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="panel-user", password="x")
        self.request = RequestFactory().get("/")
        self.request.user = self.user

    def tearDown(self):
        for key in ("visible", "hidden", "late"):
            unregister_panel(SLOT, key)

    def test_panels_are_ordered_and_can_hide_themselves(self):
        register_panel(ExtensionPanel(SLOT, "late", "bench/home.html", lambda r, o: {}, order=200))
        register_panel(ExtensionPanel(SLOT, "visible", "bench/home.html", lambda r, o: {"value": o}, order=10))
        register_panel(ExtensionPanel(SLOT, "hidden", "bench/home.html", lambda r, o: None))

        panels = panels_for(SLOT, self.request, obj=42)

        self.assertEqual([p["key"] for p in panels], ["visible", "late"])
        self.assertEqual(panels[0]["context"], {"value": 42})

    def test_registering_the_same_key_replaces_the_panel(self):
        register_panel(ExtensionPanel(SLOT, "visible", "a.html", lambda r, o: {}))
        register_panel(ExtensionPanel(SLOT, "visible", "b.html", lambda r, o: {}))

        self.assertEqual([p["template"] for p in panels_for(SLOT, self.request)], ["b.html"])

    def test_template_tag_renders_nothing_for_an_empty_slot(self):
        html = Template('{% load extension_panels %}{% extension_panels "empty.slot" %}').render(
            Context({"request": self.request})
        )
        self.assertEqual(html, "")

    def test_panel_without_slot_is_rejected(self):
        with self.assertRaises(ValueError):
            register_panel(ExtensionPanel("", "x", "a.html", lambda r, o: {}))
