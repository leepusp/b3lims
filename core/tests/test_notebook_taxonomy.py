"""Statuses and categories per research group."""

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import NotebookCategory, NotebookStatus, ResearchGroup
from core.models.lab_tools.notebook import NotebookEntry
from core.services import notebook_taxonomy as svc
from core.services.notebook_search import SearchSyntaxError, build_query


@override_settings(FORCE_SCRIPT_NAME=None)
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("root", "r@x.y", "x")
        cls.coord = User.objects.create_user("coord", password="x")
        cls.member = User.objects.create_user("member", password="x")
        cls.outsider = User.objects.create_user("outsider", password="x")
        cls.group = ResearchGroup.objects.create(name="Phage lab", coordinator=cls.coord)
        cls.group.members.add(cls.member)
        cls.other = ResearchGroup.objects.create(name="Other lab", coordinator=cls.outsider)

    def entry(self, **kw):
        kw.setdefault("author", self.member)
        kw.setdefault("title", "E")
        return NotebookEntry.objects.create(**kw)

    def post(self, user, payload, url="notebook_taxonomy_api"):
        self.client.force_login(user)
        return self.client.post(reverse(url), json.dumps(payload), content_type="application/json")


class SeedTests(Base):
    def test_migration_seeds_the_five_lab_statuses(self):
        slugs = list(NotebookStatus.objects.filter(research_group__isnull=True).values_list("slug", flat=True))
        self.assertEqual(slugs, ["draft", "in_progress", "completed", "reviewed", "archived"])

    def test_group_without_own_list_uses_the_lab_list(self):
        self.assertEqual(svc.statuses_for(self.group).count(), 5)

    def test_group_with_own_list_uses_only_it(self):
        mine = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        self.assertEqual(list(svc.statuses_for(self.group)), [mine])
        self.assertEqual(svc.statuses_for(None).count(), 5)  # positive control: the lab list is untouched


class PermissionTests(Base):
    def test_coordinator_edits_own_group_only(self):
        svc.create_category(user=self.coord, group=self.group, name="PCR", color="#aabbcc")
        with self.assertRaises(PermissionDenied):
            svc.create_category(user=self.coord, group=self.other, name="PCR", color="#aabbcc")
        with self.assertRaises(PermissionDenied):
            svc.create_category(user=self.coord, group=None, name="PCR", color="#aabbcc")

    def test_member_cannot_edit(self):
        with self.assertRaises(PermissionDenied):
            svc.create_category(user=self.member, group=self.group, name="PCR", color="#aabbcc")

    def test_superuser_edits_lab_and_groups(self):
        svc.create_category(user=self.admin, group=None, name="Lab wide", color="#aabbcc")
        svc.create_category(user=self.admin, group=self.other, name="Theirs", color="#aabbcc")

    def test_page_is_closed_to_ordinary_members(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("notebook_taxonomy")).status_code, 403)
        self.client.force_login(self.coord)
        self.assertEqual(self.client.get(reverse("notebook_taxonomy")).status_code, 200)


class ValidationTests(Base):
    def test_colour_and_name_rules(self):
        for bad in ("red", "#12", "#GGGGGG", ""):
            with self.assertRaises(ValidationError):
                svc.create_category(user=self.admin, group=None, name="X", color=bad)
        with self.assertRaises(ValidationError):
            svc.create_category(user=self.admin, group=None, name="  ", color="#aabbcc")

    def test_duplicate_names_are_refused_per_list_but_allowed_across_lists(self):
        svc.create_category(user=self.admin, group=self.group, name="PCR", color="#aabbcc")
        with self.assertRaises(ValidationError):
            svc.create_category(user=self.admin, group=self.group, name="pcr", color="#aabbcc")
        svc.create_category(user=self.admin, group=self.other, name="PCR", color="#aabbcc")

    def test_builtin_statuses_cannot_be_removed(self):
        for slug in ("draft", "archived"):
            with self.assertRaises(ValidationError):
                svc.delete_status(user=self.admin, status=NotebookStatus.objects.get(slug=slug))
        svc.delete_status(user=self.admin, status=NotebookStatus.objects.get(slug="reviewed"))  # control

    def test_deleting_a_status_moves_entries_to_draft(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        entry = self.entry(research_group=self.group, status=st.slug)
        svc.delete_status(user=self.coord, status=st)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_deleting_a_category_keeps_the_entry(self):
        cat = svc.create_category(user=self.coord, group=self.group, name="PCR", color="#aabbcc")
        entry = self.entry(research_group=self.group, category=cat)
        svc.delete_category(user=self.coord, category=cat)
        entry.refresh_from_db()
        self.assertIsNone(entry.category)

    def test_reorder_requires_every_item(self):
        a = svc.create_category(user=self.admin, group=None, name="A", color="#aabbcc")
        b = svc.create_category(user=self.admin, group=None, name="B", color="#aabbcc")
        svc.reorder(user=self.admin, model=NotebookCategory, group=None, ids=[b.pk, a.pk])
        self.assertEqual(list(NotebookCategory.objects.values_list("name", flat=True)), ["B", "A"])
        with self.assertRaises(ValidationError):
            svc.reorder(user=self.admin, model=NotebookCategory, group=None, ids=[a.pk])


class EntryApiTests(Base):
    def update(self, entry, user, payload):
        self.client.force_login(user)
        return self.client.post(
            reverse("notebook_entry_update_api", args=[entry.pk]), json.dumps(payload), content_type="application/json"
        )

    def test_group_status_is_accepted_only_for_that_group(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        entry = self.entry()
        self.assertEqual(self.update(entry, self.member, {"status": st.slug}).status_code, 400)  # lab list
        self.assertEqual(self.update(entry, self.member, {"research_group": self.group.pk}).status_code, 200)
        self.assertEqual(self.update(entry, self.member, {"status": st.slug}).status_code, 200)  # control
        entry.refresh_from_db()
        self.assertEqual(entry.status, st.slug)

    def test_moving_to_a_group_resets_a_status_that_does_not_exist_there(self):
        svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        entry = self.entry(status="completed")
        self.update(entry, self.member, {"research_group": self.group.pk})
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_cannot_file_under_a_group_you_are_not_in(self):
        entry = self.entry()
        self.assertEqual(self.update(entry, self.member, {"research_group": self.other.pk}).status_code, 400)
        entry.refresh_from_db()
        self.assertIsNone(entry.research_group)

    def test_category_must_belong_to_the_entry_list(self):
        theirs = svc.create_category(user=self.admin, group=self.other, name="Theirs", color="#aabbcc")
        mine = svc.create_category(user=self.admin, group=None, name="Mine", color="#aabbcc")
        entry = self.entry()
        self.assertEqual(self.update(entry, self.member, {"category": theirs.pk}).status_code, 400)
        self.assertEqual(self.update(entry, self.member, {"category": mine.pk}).status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.category_id, mine.pk)

    def test_changing_group_clears_a_category_from_the_old_list(self):
        mine = svc.create_category(user=self.admin, group=None, name="Mine", color="#aabbcc")
        svc.create_category(user=self.admin, group=self.group, name="Own", color="#aabbcc")
        entry = self.entry(category=mine)
        self.update(entry, self.member, {"research_group": self.group.pk})
        entry.refresh_from_db()
        self.assertIsNone(entry.category)

    def test_entry_page_renders_with_group_colours(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        entry = self.entry(research_group=self.group, status=st.slug)
        self.client.force_login(self.member)
        html = self.client.get(reverse("notebook_entry", args=[entry.pk])).content.decode()
        self.assertIn("--st: #112233", html)
        self.assertIn("Sequencing", html)


class ApiTests(Base):
    def test_coordinator_adds_status_through_the_api(self):
        r = self.post(self.coord, {"action": "add_status", "group": str(self.group.pk), "name": "Sequencing",
                                   "color": "#112233", "kind": "active"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Sequencing", [s["name"] for s in r.json()["statuses"]])

    def test_member_gets_403_and_nothing_is_created(self):
        r = self.post(self.member, {"action": "add_status", "group": str(self.group.pk), "name": "Sequencing"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(NotebookStatus.objects.filter(name="Sequencing").exists())

    def test_cannot_edit_another_groups_item_by_id(self):
        cat = svc.create_category(user=self.admin, group=self.other, name="Theirs", color="#aabbcc")
        r = self.post(self.coord, {"action": "edit_category", "group": str(self.group.pk), "id": cat.pk, "name": "Hacked"})
        self.assertEqual(r.status_code, 404)
        cat.refresh_from_db()
        self.assertEqual(cat.name, "Theirs")


class DashboardAndSearchTests(Base):
    def test_dashboard_counts_by_kind_not_by_slug(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        self.entry(research_group=self.group, status=st.slug)
        self.client.force_login(self.member)
        r = self.client.get(reverse("notebook_dashboard"))
        self.assertEqual(r.context["stats"]["in_progress"], 1)

    def test_dashboard_filters_by_group_status(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        keep = self.entry(research_group=self.group, status=st.slug, title="keep")
        self.entry(title="other")
        self.client.force_login(self.member)
        r = self.client.get(reverse("notebook_dashboard"), {"status": st.slug})
        self.assertEqual([e.pk for e in r.context["page"]], [keep.pk])

    def test_search_by_custom_status_and_category(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Wet lab", color="#112233", kind="active")
        cat = svc.create_category(user=self.coord, group=self.group, name="Cloning", color="#aabbcc")
        hit = self.entry(research_group=self.group, status=st.slug, category=cat)
        miss = self.entry()
        for text in ("status:wet_lab", "category:cloning"):
            q, structured = build_query(text, self.member)
            self.assertTrue(structured)
            ids = set(NotebookEntry.objects.filter(q).values_list("pk", flat=True))
            self.assertEqual(ids, {hit.pk}, text)
            self.assertNotIn(miss.pk, ids)

    def test_search_unknown_category_explains(self):
        with self.assertRaises(SearchSyntaxError):
            build_query("category:nothing", self.member)

    def test_batch_status_skips_entries_whose_list_lacks_it(self):
        st = svc.create_status(user=self.coord, group=self.group, name="Sequencing", color="#112233", kind="active")
        inside = self.entry(research_group=self.group)
        outside = self.entry()
        self.client.force_login(self.member)
        r = self.client.post(
            reverse("notebook_dashboard_batch_api"),
            json.dumps({"action": "status", "value": st.slug, "ids": [inside.pk, outside.pk]}),
            content_type="application/json",
        )
        self.assertEqual(r.json()["changed"], 1)
        inside.refresh_from_db(); outside.refresh_from_db()
        self.assertEqual((inside.status, outside.status), (st.slug, "draft"))
