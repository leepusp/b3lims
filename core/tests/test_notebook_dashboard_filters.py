"""Dashboard filters: category, group, tag, keyword, chips and the tags panel."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import NotebookCategory, ResearchGroup, Tag
from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_composer import NotebookFavoriteTag
from core.services import notebook_composer as composer


class DashboardFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ana = User.objects.create_user(username="df-ana", password="x")
        cls.bob = User.objects.create_user(username="df-bob", password="x")
        cls.group = ResearchGroup.objects.create(name="Df Group", coordinator=cls.ana)
        cls.other_group = ResearchGroup.objects.create(name="Df Hidden", coordinator=cls.bob)
        cls.cat = NotebookCategory.objects.create(name="Cloning")
        cls.hidden_cat = NotebookCategory.objects.create(name="Hidden cat", research_group=cls.other_group)
        cls.a = NotebookEntry.objects.create(
            title="Gel A", author=cls.ana, category=cls.cat, research_group=cls.group
        )
        cls.b = NotebookEntry.objects.create(title="Gel B", author=cls.ana)
        composer.update_header(cls.a, tags=["PCR"], keywords=["Organism: E. coli"])

    def setUp(self):
        self.client.force_login(self.ana)

    def titles(self, **params):
        response = self.client.get(reverse("notebook_dashboard"), params)
        self.assertEqual(response.status_code, 200)
        return sorted(e.title for e in response.context["page"]), response

    def test_filters_narrow_the_list(self):
        kv = self.a.keywords.first()
        self.assertEqual(self.titles()[0], ["Gel A", "Gel B"])
        self.assertEqual(self.titles(category=self.cat.pk)[0], ["Gel A"])
        self.assertEqual(self.titles(group=self.group.pk)[0], ["Gel A"])
        self.assertEqual(self.titles(tag="pcr")[0], ["Gel A"])
        self.assertEqual(self.titles(keyword=kv.pk)[0], ["Gel A"])

    def test_bad_values_are_ignored(self):
        self.assertEqual(self.titles(category="x", group="1;drop", keyword="abc")[0], ["Gel A", "Gel B"])

    def test_chips_remove_one_filter_and_keep_the_rest(self):
        _, response = self.titles(tag="pcr", category=self.cat.pk)
        chips = {c["label"]: c["remove_url"] for c in response.context["active_chips"]}
        self.assertEqual(set(chips), {"#pcr", "Category: Cloning"})
        self.assertNotIn("tag=", chips["#pcr"])
        self.assertIn("category=", chips["#pcr"])

    def test_other_groups_names_are_not_exposed_through_ids(self):
        _, response = self.titles(group=self.other_group.pk, category=self.hidden_cat.pk)
        self.assertEqual(response.context["active_chips"], [])
        html = response.content.decode()
        self.assertNotIn("Df Hidden", html)
        self.assertNotIn("Hidden cat", html)

    def test_panel_lists_favourites_tags_and_keywords(self):
        NotebookFavoriteTag.objects.create(user=self.ana, tag=Tag.objects.get(name="PCR"), position=1)
        Tag.objects.create(name="Unused favourite")
        NotebookFavoriteTag.objects.create(user=self.ana, tag=Tag.objects.get(name="Unused favourite"), position=2)
        _, response = self.titles()
        self.assertEqual({t.name for t in response.context["favorite_cloud"]}, {"PCR", "Unused favourite"})
        self.assertEqual([str(k) for k in response.context["keyword_cloud"]][:1], [str(self.a.keywords.first())])
        html = response.content.decode()
        self.assertIn("Favourites", html)
        self.assertIn("Organism: E. coli", html)


class MyTasksCardTests(DashboardFilterTests):
    def test_one_card_with_steps_and_tasks_linked_to_entries(self):
        from datetime import timedelta

        from django.utils import timezone

        composer.add_step(self.a, "Order primers", timezone.now() + timedelta(days=1))
        response = self.client.get(reverse("notebook_dashboard"))
        html = response.content.decode()
        self.assertIn("My tasks", html)
        self.assertNotIn("Steps with deadlines", html)
        self.assertIn("Order primers", html)
        self.assertIn('id="eln-todo-entry"', html)
        self.assertEqual({e.title for e in response.context["task_entries"]}, {"Gel A", "Gel B"})

        import json

        reply = self.client.post(
            reverse("notebook_todos_api"),
            data=json.dumps({"action": "add", "text": "Run the gel", "entry_id": self.a.pk}),
            content_type="application/json",
        )
        todo = reply.json()["todos"][0]
        self.assertEqual(todo["entry_url"], reverse("notebook_entry", args=[self.a.pk]))
