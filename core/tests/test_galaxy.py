"""Galaxy tools as workflow steps: catalog reading, the Galaxy step and the Galaxy templates."""

import json
from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from core.models.lab_tools.workflow import Workflow
from core.services import galaxy
from core.services import workflow_templates as templates
from core.tests.test_submissions import SubmissionBase

PANEL = [
    {"model_class": "ToolSection", "name": "Genome annotation", "elems": [
        {"model_class": "Tool", "id": "davinci_bakta", "name": "Bakta", "version": "1.12.1", "description": "annotate bacteria"},
        {"model_class": "Tool", "id": "toolshed.g2.bx.psu.edu/repos/iuc/prokka/prokka/1.14.5", "name": "Prokka", "version": "1.14.5", "description": "annotate"},
        {"model_class": "Tool", "id": "toolshed.g2.bx.psu.edu/repos/iuc/prokka/prokka/1.14.6", "name": "Prokka", "version": "1.14.6", "description": "annotate"},
        {"model_class": "Tool", "id": "secret", "name": "Hidden", "hidden": "true"},
    ]},
    {"model_class": "ToolSection", "name": "Built-in Converters", "elems": [{"model_class": "Tool", "id": "conv", "name": "Convert"}]},
    {"model_class": "Tool", "id": "upload1", "name": "Upload"},
]


def fake_catalog():
    cache.clear()
    return mock.patch.object(galaxy, "_fetch_json", return_value=PANEL)


class CatalogTests(SubmissionBase):
    def test_normalise_flattens_sections_and_hides_converters_and_hidden(self):
        with fake_catalog():
            tools = galaxy.tool_catalog(refresh=True)

        ids = [t["id"] for t in tools]

        self.assertIn("davinci_bakta", ids)
        self.assertNotIn("conv", ids)
        self.assertNotIn("secret", ids)
        self.assertEqual(next(t for t in tools if t["id"] == "upload1")["section"], "Other")
        self.assertTrue(next(t for t in tools if t["id"] == "davinci_bakta")["custom"])
        self.assertEqual(galaxy.tool_url("davinci_bakta"), "/galaxy/tool_runner?tool_id=davinci_bakta")

    def test_resolve_picks_newest_version_and_find_is_exact(self):
        with fake_catalog():
            self.assertTrue(galaxy.resolve_tool("toolshed.g2.bx.psu.edu/repos/iuc/prokka/prokka").get("id").endswith("1.14.6"))
            self.assertIsNone(galaxy.resolve_tool("nothing"))
            self.assertIsNotNone(galaxy.find_tool("davinci_bakta"))
            self.assertIsNone(galaxy.find_tool("davinci"))

    def test_unavailable_galaxy_is_reported_not_raised(self):
        cache.clear()
        with mock.patch.object(galaxy, "_fetch_json", side_effect=galaxy.GalaxyUnavailable("down")):
            self.client.force_login(self.ana)
            data = self.client.get(reverse("workflow_galaxy_tools_api")).json()

            self.assertEqual(data["status"], "unavailable")
            self.assertIsNone(galaxy.find_tool("davinci_bakta"))

    def test_result_link_rules(self):
        self.assertEqual(galaxy.clean_result_link(""), "")
        self.assertEqual(galaxy.clean_result_link("https://x.org/a?b=1"), "https://x.org/a?b=1")
        self.assertEqual(galaxy.clean_result_link("/galaxy/histories/view?id=1"), "/galaxy/histories/view?id=1")
        for bad in ("http://x.org", "//x.org", "javascript:alert(1)", "https://x.org/a b"):
            with self.subTest(bad), self.assertRaises(Exception):
                galaxy.clean_result_link(bad)


class GalaxyStepTests(SubmissionBase):
    def setUp(self):
        super().setUp()
        self.workflow = Workflow.objects.create(name="G", owner=self.ana)
        self.client.force_login(self.ana)

    def post(self, payload, workflow=None):
        return self.client.post(reverse("workflow_api", args=[(workflow or self.workflow).pk]), json.dumps(payload), content_type="application/json")

    def test_tools_api_lists_tools(self):
        with fake_catalog():
            data = self.client.get(reverse("workflow_galaxy_tools_api")).json()

        self.assertEqual(data["status"], "success")
        self.assertIn("davinci_bakta", [t["id"] for t in data["tools"]])

    def test_add_galaxy_step_and_its_info(self):
        with fake_catalog():
            response = self.post({"action": "add_galaxy_step", "tool_id": "davinci_bakta", "x": 10, "y": 20})

        self.assertEqual(response.status_code, 200, response.content)

        step = self.workflow.steps.get(pk=response.json()["step_id"])
        info = next(s for s in response.json()["workflow"]["steps"] if s["id"] == step.pk)["galaxy"]

        self.assertEqual(step.kind, "galaxy")
        self.assertEqual(info["name"], "Bakta")
        self.assertEqual(info["tool_url"], "/galaxy/tool_runner?tool_id=davinci_bakta")

    def test_unknown_tool_is_refused(self):
        with fake_catalog():
            response = self.post({"action": "add_galaxy_step", "tool_id": "nope"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.workflow.steps.count(), 0)

    def test_kind_is_locked_and_result_link_saved(self):
        with fake_catalog():
            step_id = self.post({"action": "add_galaxy_step", "tool_id": "davinci_bakta"}).json()["step_id"]

        response = self.post({"action": "update_step", "step_id": step_id, "step": {"kind": "manual", "galaxy_url": "https://davinci.icb.usp.br/galaxy/histories/view?id=9", "result_note": "done"}})
        step = self.workflow.steps.get(pk=step_id)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(step.kind, "galaxy")
        self.assertEqual(step.config["galaxy_url"], "https://davinci.icb.usp.br/galaxy/histories/view?id=9")

        bad = self.post({"action": "update_step", "step_id": step_id, "step": {"galaxy_url": "http://evil"}})

        self.assertEqual(bad.status_code, 400)

    def test_galaxy_kind_cannot_be_created_by_hand(self):
        response = self.post({"action": "add_step", "step": {"title": "x", "kind": "galaxy"}})

        self.assertEqual(response.status_code, 400)


class GalaxyTemplateTests(SubmissionBase):
    def build(self, key):
        wf = Workflow.objects.create(name=key, owner=self.ana)
        self.client.force_login(self.ana)
        response = self.client.post(reverse("workflow_api", args=[wf.pk]), json.dumps({"action": "apply_template", "template": key}), content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)

        return wf

    def test_templates_use_galaxy_steps_when_tools_exist(self):
        with mock.patch.object(galaxy, "resolve_tool", side_effect=lambda spec: {"id": spec, "name": spec.split("/")[-1], "version": "1", "section": "S", "description": "", "url": galaxy.tool_url(spec), "custom": False}):
            wf = self.build("galaxy_align_tree")

        self.assertTrue(wf.steps.filter(kind="galaxy").exists())

    def test_templates_fall_back_to_plain_steps_when_tool_missing(self):
        with mock.patch.object(galaxy, "resolve_tool", return_value=None):
            wf = self.build("galaxy_align_tree")

        self.assertFalse(wf.steps.filter(kind="galaxy").exists())
        self.assertTrue(wf.steps.filter(notes__contains="not found in the Galaxy catalog").exists())

    def test_galaxy_templates_listed_in_catalog(self):
        self.assertTrue([w for w in templates.catalog()["workflows"] if w["category"] == "Galaxy"])
