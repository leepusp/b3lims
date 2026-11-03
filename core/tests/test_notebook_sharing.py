"""Sharing Notebook entries with users and research groups."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import ResearchGroup, ResourceAccessGrant
from core.models.lab_tools.notebook import NotebookEntry
from core.permissions.notebook import (
    can_delete_notebook_entry,
    can_edit_notebook_entry,
    can_manage_notebook_entry_sharing,
    can_view_notebook_entry,
    shared_with_user,
    visible_notebook_entries_for_user,
)
from core.services import notebook_sharing as svc


@override_settings(FORCE_SCRIPT_NAME=None)
class SharingBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user("author", first_name="Ada", last_name="Author", password="x")
        cls.ana = User.objects.create_user("ana", password="x")
        cls.bob = User.objects.create_user("bob", password="x")
        cls.eve = User.objects.create_user("eve", password="x")
        cls.admin = User.objects.create_superuser("root", "r@x.y", "x")
        cls.group = ResearchGroup.objects.create(name="Phage lab", coordinator=cls.ana)
        cls.group.members.add(cls.bob)

    def make(self, visibility="private", **kw):
        return NotebookEntry.objects.create(title="E", author=self.author, visibility=visibility, **kw)

    def share(self, entry, user=None, group=None, level="view", **kw):
        return svc.share_entry(entry=entry, granted_by=self.author, level=level, user=user,
                               research_group=group, **kw)

    def sees(self, user, entry):
        return visible_notebook_entries_for_user(user).filter(pk=entry.pk).exists()


class VisibilityRulesTests(SharingBase):
    def test_private_entry_is_only_the_authors(self):
        entry = self.make("private")
        self.assertTrue(self.sees(self.author, entry))
        self.assertFalse(self.sees(self.ana, entry))
        self.assertFalse(can_view_notebook_entry(self.ana, entry))
        self.assertTrue(self.sees(self.admin, entry))

    def test_shared_without_grants_is_still_only_the_author(self):
        entry = self.make("shared")
        self.assertFalse(self.sees(self.ana, entry))

    def test_grant_makes_a_shared_entry_visible_to_that_user_only(self):
        entry = self.make("shared")
        self.share(entry, user=self.ana)
        self.assertTrue(self.sees(self.ana, entry))      # positive control
        self.assertTrue(can_view_notebook_entry(self.ana, entry))
        self.assertFalse(self.sees(self.eve, entry))
        self.assertFalse(can_view_notebook_entry(self.eve, entry))

    def test_group_grant_reaches_members_and_the_coordinator(self):
        entry = self.make("shared")
        self.share(entry, group=self.group)
        self.assertTrue(self.sees(self.bob, entry))      # member
        self.assertTrue(self.sees(self.ana, entry))      # coordinator
        self.assertFalse(self.sees(self.eve, entry))

    def test_sharing_a_private_entry_turns_it_shared(self):
        entry = self.make("private")
        self.share(entry, user=self.ana)
        entry.refresh_from_db()
        self.assertEqual(entry.visibility, "shared")
        self.assertTrue(self.sees(self.ana, entry))

    def test_grants_do_not_leak_when_the_author_sets_it_back_to_private(self):
        entry = self.make("private")
        self.share(entry, user=self.ana)
        svc.set_visibility(entry=entry, value="private", changed_by=self.author)
        self.assertFalse(self.sees(self.ana, entry))
        self.assertFalse(can_view_notebook_entry(self.ana, entry))
        self.assertFalse(can_edit_notebook_entry(self.ana, entry))

    def test_revoked_and_expired_grants_stop_working(self):
        entry = self.make("shared")
        grant = self.share(entry, user=self.ana)
        self.assertTrue(self.sees(self.ana, entry))
        svc.unshare_entry(entry=entry, grant_id=grant.pk, revoked_by=self.author)
        self.assertFalse(self.sees(self.ana, entry))
        self.assertFalse(can_view_notebook_entry(self.ana, entry))

        grant = self.share(entry, user=self.bob)
        ResourceAccessGrant.objects.filter(pk=grant.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        self.assertFalse(self.sees(self.bob, entry))
        self.assertFalse(can_view_notebook_entry(self.bob, entry))

    def test_trashed_entry_is_hidden_even_with_a_grant(self):
        entry = self.make("shared")
        self.share(entry, user=self.ana)
        entry.deleted_at = timezone.now()
        entry.save()
        self.assertFalse(self.sees(self.ana, entry))
        self.assertFalse(can_view_notebook_entry(self.ana, entry))
        self.assertFalse(can_edit_notebook_entry(self.ana, entry))

    def test_grant_on_another_entry_does_not_help(self):
        mine, other = self.make("shared"), self.make("shared")
        self.share(mine, user=self.ana)
        self.assertTrue(self.sees(self.ana, mine))
        self.assertFalse(self.sees(self.ana, other))

    def test_shared_with_user_lists_only_granted_entries(self):
        granted, lab = self.make("shared"), self.make("lab")
        self.share(granted, user=self.ana)
        listed = set(shared_with_user(self.ana).values_list("pk", flat=True))
        self.assertEqual(listed, {granted.pk})
        self.assertNotIn(lab.pk, listed)


class AccessLevelTests(SharingBase):
    def test_levels(self):
        entry = self.make("shared")
        self.share(entry, user=self.ana, level="view")
        self.share(entry, user=self.bob, level="edit")
        self.share(entry, user=self.eve, level="manage")
        flags = lambda u: (can_view_notebook_entry(u, entry), can_edit_notebook_entry(u, entry),
                           can_manage_notebook_entry_sharing(u, entry), can_delete_notebook_entry(u, entry))
        self.assertEqual(flags(self.ana), (True, False, False, False))
        self.assertEqual(flags(self.bob), (True, True, False, False))
        self.assertEqual(flags(self.eve), (True, True, True, False))
        self.assertEqual(flags(self.author), (True, True, True, True))
        self.assertEqual(flags(self.admin), (True, True, True, True))

    def test_highest_level_wins_between_user_and_group(self):
        entry = self.make("shared")
        self.share(entry, user=self.bob, level="view")
        self.share(entry, group=self.group, level="edit")
        self.assertTrue(can_edit_notebook_entry(self.bob, entry))

    def test_lab_entry_can_have_extra_editors(self):
        entry = self.make("lab")
        self.assertFalse(can_edit_notebook_entry(self.ana, entry))
        self.share(entry, user=self.ana, level="edit")
        self.assertTrue(can_edit_notebook_entry(self.ana, entry))
        self.assertFalse(can_edit_notebook_entry(self.eve, entry))

    def test_updating_a_grant_changes_the_level_without_duplicates(self):
        entry = self.make("shared")
        self.share(entry, user=self.ana, level="view")
        self.share(entry, user=self.ana, level="edit")
        self.assertEqual(len(svc.entry_grants(entry)), 1)
        self.assertTrue(can_edit_notebook_entry(self.ana, entry))


class ServiceRuleTests(SharingBase):
    def test_only_managers_can_share(self):
        entry = self.make("shared")
        with self.assertRaises(PermissionDenied):
            svc.share_entry(entry=entry, granted_by=self.ana, level="view", user=self.bob)
        self.share(entry, user=self.ana, level="edit")
        with self.assertRaises(PermissionDenied):      # edit is not enough
            svc.share_entry(entry=entry, granted_by=self.ana, level="view", user=self.bob)
        self.share(entry, user=self.ana, level="manage")
        svc.share_entry(entry=entry, granted_by=self.ana, level="view", user=self.bob)
        self.assertTrue(can_view_notebook_entry(self.bob, entry))

    def test_validation(self):
        entry = self.make("shared")
        with self.assertRaisesMessage(ValidationError, "author already"):
            self.share(entry, user=self.author)
        with self.assertRaisesMessage(ValidationError, "valid access level"):
            self.share(entry, user=self.ana, level="owner")
        with self.assertRaisesMessage(ValidationError, "future"):
            self.share(entry, user=self.ana, expires_at=timezone.now() - timedelta(days=1))
        self.ana.is_active = False
        self.ana.save()
        with self.assertRaisesMessage(ValidationError, "inactive"):
            self.share(entry, user=self.ana)
        entry.deleted_at = timezone.now()
        entry.save()
        with self.assertRaisesMessage(ValidationError, "trash"):
            self.share(entry, user=self.bob)

    def test_a_manager_cannot_open_the_entry_to_the_lab_or_make_it_private(self):
        entry = self.make("shared")
        self.share(entry, user=self.ana, level="manage")
        with self.assertRaises(PermissionDenied):
            svc.set_visibility(entry=entry, value="lab", changed_by=self.ana)
        with self.assertRaises(PermissionDenied):
            svc.set_visibility(entry=entry, value="private", changed_by=self.ana)
        svc.set_visibility(entry=entry, value="lab", changed_by=self.author)
        entry.refresh_from_db()
        self.assertEqual(entry.visibility, "lab")

    def test_search_excludes_author_and_inactive_and_needs_two_letters(self):
        entry = self.make("shared")
        names = [(r["kind"], r["name"]) for r in svc.search_principals(query="a", entry=entry)]
        self.assertEqual(names, [])
        found = svc.search_principals(query="an", entry=entry)
        self.assertIn(("user", "ana"), [(r["kind"], r["name"]) for r in found])
        self.assertNotIn("author", [r["detail"] for r in svc.search_principals(query="auth", entry=entry)])
        self.bob.is_active = False
        self.bob.save()
        self.assertEqual([r for r in svc.search_principals(query="bob", entry=entry)], [])
        self.assertIn(("group", "Phage lab"),
                      [(r["kind"], r["name"]) for r in svc.search_principals(query="phage", entry=entry)])


class SharingApiTests(SharingBase):
    def setUp(self):
        self.entry = self.make("private")
        self.url = reverse("notebook_sharing_api", args=[self.entry.pk])
        self.client.force_login(self.author)

    def post(self, body, user=None):
        if user:
            self.client.force_login(user)
        return self.client.post(self.url, json.dumps(body), content_type="application/json")

    def test_grant_list_and_revoke_round_trip(self):
        r = self.post({"action": "grant", "kind": "user", "principal_id": self.ana.pk, "level": "edit"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["visibility"], "shared")
        self.assertEqual([(g["name"], g["level"]) for g in data["grants"]], [("ana", "edit")])
        r = self.post({"action": "grant", "kind": "group", "principal_id": self.group.pk, "level": "view"})
        self.assertEqual({g["kind"] for g in r.json()["grants"]}, {"user", "group"})
        gid = [g["id"] for g in r.json()["grants"] if g["kind"] == "user"][0]
        r = self.post({"action": "revoke", "grant_id": gid})
        self.assertEqual([g["kind"] for g in r.json()["grants"]], ["group"])

    def test_expiry_date_is_stored_and_validated(self):
        future = (timezone.localdate() + timedelta(days=3)).isoformat()
        r = self.post({"action": "grant", "kind": "user", "principal_id": self.ana.pk, "level": "view", "expires": future})
        self.assertEqual(r.json()["grants"][0]["expires_at"], future)
        r = self.post({"action": "grant", "kind": "user", "principal_id": self.bob.pk, "level": "view", "expires": "soon"})
        self.assertEqual(r.status_code, 400)
        r = self.post({"action": "grant", "kind": "user", "principal_id": self.bob.pk, "level": "view",
                       "expires": (timezone.localdate() - timedelta(days=1)).isoformat()})
        self.assertEqual(r.status_code, 400)

    def test_errors_are_json(self):
        for body in ({"action": "nope"}, {"action": "grant", "kind": "alien"},
                     {"action": "grant", "kind": "user", "principal_id": self.ana.pk, "level": "x"},
                     {"action": "revoke", "grant_id": 99999}, {"action": "visibility", "value": "x"}):
            with self.subTest(body=body):
                r = self.post(body)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.json()["status"], "error")
        r = self.client.post(self.url, "{bad", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_stranger_cannot_even_see_the_state(self):
        self.client.force_login(self.eve)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_viewer_sees_state_but_not_the_list_and_cannot_change_it(self):
        self.post({"action": "grant", "kind": "user", "principal_id": self.ana.pk, "level": "view"})
        self.post({"action": "grant", "kind": "user", "principal_id": self.bob.pk, "level": "view"})
        self.client.force_login(self.ana)
        state = self.client.get(self.url).json()
        self.assertFalse(state["can_manage"])
        self.assertEqual(state["grants"], [])
        self.assertEqual(state["your_access"], "view")
        self.assertEqual(self.client.get(self.url + "?q=bo").status_code, 403)
        r = self.post({"action": "grant", "kind": "user", "principal_id": self.eve.pk, "level": "view"}, user=self.ana)
        self.assertEqual(r.status_code, 403)
        self.client.force_login(self.eve)
        self.assertEqual(self.client.get(self.url).status_code, 404)  # still no access

    def test_lookup_endpoint_for_managers(self):
        r = self.client.get(self.url + "?q=an")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ana", [x["detail"] for x in r.json()["results"]])


class EntryPagePermissionTests(SharingBase):
    def setUp(self):
        self.entry = self.make("shared", content="<p>hello</p>")
        self.share(self.entry, user=self.ana, level="edit")
        self.share(self.entry, user=self.bob, level="view")
        self.update_url = reverse("notebook_entry_update_api", args=[self.entry.pk])

    def update(self, user, body):
        self.client.force_login(user)
        return self.client.post(self.update_url, json.dumps(body), content_type="application/json")

    def test_editor_can_change_content_viewer_cannot(self):
        self.assertEqual(self.update(self.ana, {"title": "By Ana"}).status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, "By Ana")
        self.assertEqual(self.update(self.bob, {"title": "By Bob"}).status_code, 403)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, "By Ana")

    def test_editor_cannot_change_visibility(self):
        r = self.update(self.ana, {"visibility": "lab"})
        self.assertEqual(r.status_code, 403)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.visibility, "shared")
        self.assertEqual(self.update(self.author, {"visibility": "lab"}).status_code, 200)

    def test_editor_saving_with_unchanged_visibility_is_fine(self):
        self.assertEqual(self.update(self.ana, {"title": "T", "visibility": "shared"}).status_code, 200)

    def test_page_flags(self):
        url = reverse("notebook_entry", args=[self.entry.pk])
        for user, can_edit, can_share, can_delete in (
            (self.author, True, True, True),
            (self.ana, True, False, False),
            (self.bob, False, False, False),
        ):
            self.client.force_login(user)
            ctx = self.client.get(url).context
            self.assertEqual((ctx["can_edit"], ctx["can_share"], ctx["can_delete"]), (can_edit, can_share, can_delete),
                             user.username)
        self.client.force_login(self.ana)
        html = self.client.get(url).content.decode()
        self.assertNotIn('id="bx-trash"', html)
        self.assertIn('id="bx-share"', html)

    def test_editor_cannot_trash_the_authors_entry_but_author_can(self):
        batch = reverse("notebook_dashboard_batch_api")
        self.client.force_login(self.ana)
        r = self.client.post(batch, json.dumps({"action": "trash", "ids": [self.entry.pk]}), content_type="application/json")
        self.assertEqual(r.json()["changed"], 0)
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.deleted_at)
        self.client.force_login(self.author)
        r = self.client.post(batch, json.dumps({"action": "trash", "ids": [self.entry.pk]}), content_type="application/json")
        self.assertEqual(r.json()["changed"], 1)

    def test_editor_can_change_status_in_batch(self):
        batch = reverse("notebook_dashboard_batch_api")
        self.client.force_login(self.ana)
        r = self.client.post(batch, json.dumps({"action": "status", "value": "completed", "ids": [self.entry.pk]}),
                             content_type="application/json")
        self.assertEqual(r.json()["changed"], 1)

    def test_dashboard_lists_entries_shared_with_me(self):
        self.client.force_login(self.ana)
        r = self.client.get(reverse("notebook_dashboard"))
        self.assertIn(self.entry.pk, [e.pk for e in r.context["page"].object_list])
        self.client.force_login(self.eve)
        r = self.client.get(reverse("notebook_dashboard"))
        self.assertNotIn(self.entry.pk, [e.pk for e in r.context["page"].object_list])
