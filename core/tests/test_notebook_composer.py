"""B3 Bench 1.A — eLabFTW-style composition of Notebook entries."""

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Sample
from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_composer import NotebookEntryLink, NotebookStep
from core.services import notebook_composer as composer


def field(kind, value="", **extra):
    return {"type": kind, "value": value, **extra}


@override_settings(FORCE_SCRIPT_NAME=None)
class ComposerTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="composer-owner", password="x")
        cls.other = User.objects.create_user(username="composer-other", password="x")
        cls.entry = NotebookEntry.objects.create(title="Plaque assay", author=cls.owner)
        cls.private_other = NotebookEntry.objects.create(
            title="Someone else's private entry", author=cls.other, visibility="private"
        )
        cls.lab_entry = NotebookEntry.objects.create(
            title="Lysate prep", author=cls.other, visibility="lab", custom_id="EXP-024"
        )
        cls.sample = Sample.objects.create(
            sample_id="B3-S-000142", sample_type="Bacteria",
            organism_name="Xanthomonas citri 306", owner=cls.owner,
        )
        cls.hidden_sample = Sample.objects.create(
            sample_id="B3-S-HIDDEN", sample_type="Bacteria", owner=cls.other,
        )

    def normalize(self, fields, groups=None):
        return composer.normalize_metadata(
            {"extra_fields": fields, "elabftw": {"extra_fields_groups": groups or []}},
            user=self.owner,
            entry=self.entry,
        )


class CustomFieldRuleTests(ComposerTestBase):
    def test_metadata_uses_elabftw_layout(self):
        meta = self.normalize(
            {"Medium": field("select", "TSB", options=["TSB", "LB"], group_id=1, required=True)},
            [{"id": 1, "name": "Culture"}],
        )
        self.assertEqual(meta["elabftw"]["extra_fields_groups"], [{"id": 1, "name": "Culture"}])
        self.assertEqual(meta["extra_fields"]["Medium"]["value"], "TSB")
        self.assertTrue(meta["extra_fields"]["Medium"]["required"])
        self.assertEqual(meta["extra_fields"]["Medium"]["position"], 0)

    def test_value_types_are_validated(self):
        good = {
            "t": field("text", "hello"),
            "n": field("number", "28,5", units=["°C", "K"], unit="K"),
            "c": field("checkbox", "on"),
            "d": field("date", "2026-11-02"),
            "dt": field("datetime-local", "2026-11-02T14:30"),
            "tm": field("time", "14:30"),
            "e": field("email", "lab@usp.br"),
            "u": field("url", "https://ena.org/x"),
            "r": field("radio", "A", options=["A", "B"]),
            "m": field("select", ["A", "B"], options=["A", "B", "C"], allow_multi_values=True),
        }
        meta = self.normalize(good)
        self.assertEqual(meta["extra_fields"]["n"]["value"], "28.5")
        self.assertEqual(meta["extra_fields"]["n"]["unit"], "K")
        self.assertEqual(meta["extra_fields"]["m"]["value"], ["A", "B"])

        bad = [
            {"n": field("number", "abc")},
            {"d": field("date", "02/11/2026")},
            {"e": field("email", "not-an-email")},
            {"u": field("url", "javascript:alert(1)")},
            {"s": field("select", "Z", options=["A"])},
            {"s": field("select", "", options=[])},
            {"x": field("script", "x")},
            {"n": field("number", "1", units=["°C"], unit="K")},
            {"g": field("text", "", group_id=9)},
        ]
        for fields in bad:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.normalize(fields)

    def test_reference_fields_respect_visibility(self):
        meta = self.normalize({"Host": field("items", self.sample.pk)})
        self.assertEqual(meta["extra_fields"]["Host"]["value"], str(self.sample.pk))

        self.normalize({"Lysate": field("experiments", self.lab_entry.pk)})

        for fields in (
            {"Host": field("items", self.hidden_sample.pk)},
            {"Prev": field("experiments", self.private_other.pk)},
            {"Who": field("users", 999999)},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.normalize(fields)

    def test_unchanged_stored_value_is_kept(self):
        self.entry.metadata = {"extra_fields": {"Host": field("items", str(self.hidden_sample.pk))}}
        meta = self.normalize({"Host": field("items", str(self.hidden_sample.pk))})
        self.assertEqual(meta["extra_fields"]["Host"]["value"], str(self.hidden_sample.pk))

    def test_unknown_metadata_keys_are_preserved(self):
        self.entry.metadata = {"external": {"ena": "PRJEB1"}}
        meta = self.normalize({"t": field("text", "x")})
        self.assertEqual(meta["external"], {"ena": "PRJEB1"})

    def test_missing_required(self):
        meta = self.normalize({"a": field("text", "", required=True), "b": field("text", "ok", required=True)})
        self.assertEqual(composer.missing_required_fields(meta), ["a"])


class ComposerApiTests(ComposerTestBase):
    def setUp(self):
        self.client.force_login(self.owner)

    def post(self, name, payload, entry=None):
        return self.client.post(
            reverse(name, args=[(entry or self.entry).pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_fields_api_saves_and_returns_state(self):
        response = self.post("notebook_fields_api", {"metadata": {
            "extra_fields": {"Host": field("items", self.sample.pk, required=True)},
        }})
        self.assertEqual(response.status_code, 200)
        state = response.json()["state"]
        self.assertIn("B3-S-000142", state["fields"]["labels"]["Host"])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.metadata["extra_fields"]["Host"]["value"], str(self.sample.pk))

    def test_fields_api_rejects_bad_value(self):
        response = self.post("notebook_fields_api", {"metadata": {"extra_fields": {"n": field("number", "x")}}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("number", response.json()["message"])

    def test_header_api_sets_tags_custom_id_and_rating(self):
        response = self.post("notebook_header_api", {"custom_id": "EXP-2026-031", "rating": 4, "tags": ["BSL2", "#bad tag<"]})
        self.assertEqual(response.status_code, 400)
        response = self.post("notebook_header_api", {"custom_id": "EXP-2026-031", "rating": 4, "tags": ["BSL2", "host-range"]})
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.custom_id, "EXP-2026-031")
        self.assertEqual(self.entry.rating, 4)
        self.assertEqual(sorted(t.name for t in self.entry.shared_tags.all()), ["BSL2", "host-range"])

    def test_steps_api_lifecycle(self):
        self.post("notebook_steps_api", {"action": "add", "body": "Dilute lysate"})
        self.post("notebook_steps_api", {"action": "add", "body": "Plate", "deadline": "2026-11-06T17:00"})
        steps = list(self.entry.steps.all())
        self.assertEqual([s.body for s in steps], ["Dilute lysate", "Plate"])

        self.post("notebook_steps_api", {"action": "update", "step_id": steps[0].pk, "finished": True})
        steps[0].refresh_from_db()
        self.assertTrue(steps[0].finished)
        self.assertEqual(steps[0].finished_by, self.owner)
        self.assertIsNotNone(steps[0].finished_at)

        self.post("notebook_steps_api", {"action": "reorder", "order": [steps[1].pk, steps[0].pk]})
        self.assertEqual([s.body for s in self.entry.steps.all()], ["Plate", "Dilute lysate"])

        self.post("notebook_steps_api", {"action": "delete", "step_id": steps[1].pk})
        self.assertEqual(self.entry.steps.count(), 1)

    def test_entry_links(self):
        response = self.post("notebook_entry_links_api", {"action": "add", "target_id": self.lab_entry.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["links"]["outgoing"][0]["id"], self.lab_entry.pk)

        for target in (self.private_other.pk, self.entry.pk):
            response = self.post("notebook_entry_links_api", {"action": "add", "target_id": target})
            self.assertEqual(response.status_code, 400)

        self.post("notebook_entry_links_api", {"action": "remove", "target_id": self.lab_entry.pk})
        self.assertFalse(NotebookEntryLink.objects.exists())

    def test_other_users_cannot_edit(self):
        self.client.force_login(self.other)
        for name, payload in (
            ("notebook_fields_api", {"metadata": {"extra_fields": {}}}),
            ("notebook_header_api", {"rating": 1}),
            ("notebook_steps_api", {"action": "add", "body": "x"}),
            ("notebook_entry_links_api", {"action": "add", "target_id": self.lab_entry.pk}),
        ):
            with self.subTest(name=name):
                self.assertIn(self.post(name, payload).status_code, {403, 404})

    def test_lookup_only_returns_visible_records(self):
        response = self.client.get(
            reverse("notebook_lookup_api", args=[self.entry.pk]), {"kind": "items", "q": "B3-S"}
        )
        ids = {r["id"] for r in response.json()["results"]}
        self.assertIn(self.sample.pk, ids)
        self.assertNotIn(self.hidden_sample.pk, ids)

        response = self.client.get(
            reverse("notebook_lookup_api", args=[self.entry.pk]), {"kind": "experiments", "q": ""}
        )
        ids = {r["id"] for r in response.json()["results"]}
        self.assertIn(self.lab_entry.pk, ids)
        self.assertNotIn(self.private_other.pk, ids)
        self.assertNotIn(self.entry.pk, ids)

    def test_load_fields_copies_structure_without_values(self):
        NotebookEntry.objects.filter(pk=self.lab_entry.pk).update(metadata={
            "extra_fields": {"Medium": field("select", "TSB", options=["TSB", "LB"])},
            "elabftw": {"extra_fields_groups": []},
        })
        response = self.client.get(reverse("notebook_field_definitions_api", args=[self.lab_entry.pk]))
        medium = response.json()["metadata"]["extra_fields"]["Medium"]
        self.assertEqual(medium["value"], "")
        self.assertEqual(medium["options"], ["TSB", "LB"])

        response = self.client.get(reverse("notebook_field_definitions_api", args=[self.private_other.pk]))
        self.assertEqual(response.status_code, 404)


@override_settings(FORCE_SCRIPT_NAME=None)
class ComposerPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="composer-page", password="x")
        self.client.force_login(self.user)

    def test_template_creates_fields_and_steps(self):
        self.client.get(reverse("notebook_create") + "?template=plasmid_construction")
        entry = NotebookEntry.objects.get(author=self.user)
        self.assertIn("Backbone", entry.metadata["extra_fields"])
        self.assertEqual(entry.metadata["elabftw"]["extra_fields_groups"][0]["name"], "Construct")
        self.assertEqual(NotebookStep.objects.filter(entry=entry).count(), 6)

    def test_page_renders_composer(self):
        self.client.get(reverse("notebook_create") + "?template=experiment")
        entry = NotebookEntry.objects.get(author=self.user)
        response = self.client.get(reverse("notebook_entry", args=[entry.pk]))
        self.assertContains(response, 'id="nb-composer"')
        self.assertContains(response, 'id="nb-composer-state"')
        self.assertContains(response, "notebook_composer_v1.js")
        self.assertContains(response, "Custom fields")


@override_settings(FORCE_SCRIPT_NAME=None)
class NotebookDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.me = User.objects.create_user(username="dash-me", password="x")
        cls.other = User.objects.create_user(username="dash-other", password="x")
        cls.mine = NotebookEntry.objects.create(title="Plaque assay", author=cls.me, status="in_progress", custom_id="EXP-031")
        cls.mine_archived = NotebookEntry.objects.create(title="Old run", author=cls.me, status="archived")
        cls.lab = NotebookEntry.objects.create(title="Lab lysate prep", author=cls.other, visibility="lab")
        cls.hidden = NotebookEntry.objects.create(title="Private of other", author=cls.other, visibility="private")
        composer.update_header(cls.mine, tags=["bsl2"])
        NotebookStep.objects.create(entry=cls.mine, body="Plate", finished=True)
        NotebookStep.objects.create(entry=cls.mine, body="Count")

    def setUp(self):
        self.client.force_login(self.me)

    def get(self, **params):
        return self.client.get(reverse("notebook_dashboard"), params)

    def titles(self, response):
        return [e.title for e in response.context["page"]]

    def test_lists_visible_active_entries(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(self.titles(response), ["Plaque assay", "Lab lysate prep"])
        self.assertContains(response, "1/2")
        self.assertContains(response, "#bsl2")

    def test_filters(self):
        self.assertEqual(self.titles(self.get(owner="me")), ["Plaque assay"])
        self.assertEqual(self.titles(self.get(state="archived")), ["Old run"])
        self.assertEqual(self.titles(self.get(tag="bsl2")), ["Plaque assay"])
        self.assertEqual(self.titles(self.get(q="EXP-031")), ["Plaque assay"])
        self.assertEqual(self.titles(self.get(q=f"#{self.lab.pk}")), ["Lab lysate prep"])
        self.assertEqual(self.titles(self.get(status="in_progress")), ["Plaque assay"])
        self.assertNotIn("Private of other", self.titles(self.get(state="all")))

    def batch(self, action, ids, value=None):
        return self.client.post(
            reverse("notebook_dashboard_batch_api"),
            data=json.dumps({"action": action, "ids": ids, "value": value}),
            content_type="application/json",
        ).json()

    def test_batch_only_changes_editable_entries(self):
        result = self.batch("status", [self.mine.pk, self.lab.pk, self.hidden.pk], "completed")
        self.assertEqual((result["changed"], result["skipped"]), (1, 2))
        self.mine.refresh_from_db(); self.lab.refresh_from_db()
        self.assertEqual(self.mine.status, "completed")
        self.assertEqual(self.lab.status, "draft")

        self.batch("add_tag", [self.mine.pk], "#Phage")
        self.assertIn("Phage", [t.name for t in self.mine.shared_tags.all()])

        self.batch("archive", [self.mine.pk])
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, "archived")

    def test_pins_are_personal_and_shown(self):
        self.batch("pin", [self.lab.pk, self.hidden.pk])
        response = self.get()
        self.assertEqual([e.title for e in response.context["pinned"]], ["Lab lysate prep"])
        self.client.force_login(self.other)
        self.assertEqual(list(self.get().context["pinned"]), [])

    def test_sidebar_points_to_dashboard(self):
        response = self.get()
        self.assertContains(response, f'href="{reverse("notebook_dashboard")}"')
