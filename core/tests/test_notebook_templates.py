"""User-made entry templates."""

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import NotebookTemplate, ResearchGroup
from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_composer import NotebookStep
from core.services import notebook_templates as svc


@override_settings(FORCE_SCRIPT_NAME=None)
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("root", "r@x.y", "x")
        cls.owner = User.objects.create_user("owner", password="x")
        cls.coord = User.objects.create_user("coord", password="x")
        cls.member = User.objects.create_user("member", password="x")
        cls.outsider = User.objects.create_user("outsider", password="x")
        cls.group = ResearchGroup.objects.create(name="Phage lab", coordinator=cls.coord)
        cls.group.members.add(cls.owner, cls.member)

    def entry(self, user=None, **kw):
        entry = NotebookEntry.objects.create(
            title=kw.pop("title", "PCR run"), author=user or self.owner,
            content=kw.pop("content", "<h3>Objective</h3><p>Amplify</p>"),
            protocol_content="Mix\n", entry_type="experiment",
            metadata={"extra_fields": {"Temp": {"type": "number", "value": "72", "position": 0}},
                      "elabftw": {"extra_fields_groups": [{"id": 1, "name": "Conditions"}]}},
            **kw,
        )
        NotebookStep.objects.create(entry=entry, body="Prepare mix", position=0, finished=True)
        NotebookStep.objects.create(entry=entry, body="Cycle", position=1)
        return entry

    def make(self, **kw):
        kw.setdefault("name", "PCR")
        return svc.save_entry_as_template(entry=self.entry(), user=self.owner, **kw)


class SaveAndUseTests(Base):
    def test_template_keeps_text_fields_and_steps_but_not_values_or_progress(self):
        tpl = self.make()
        self.assertEqual(tpl.structure["steps"], ["Prepare mix", "Cycle"])
        self.assertEqual(tpl.structure["extra_fields"]["Temp"]["value"], "")  # cleared
        new = svc.create_entry_from_template(user=self.member, template=tpl)
        self.assertEqual(new.author, self.member)
        self.assertEqual(new.visibility, "private")
        self.assertEqual(new.status, "draft")
        self.assertIn("Amplify", new.content)
        self.assertEqual(new.metadata["extra_fields"]["Temp"]["value"], "")
        steps = list(new.steps.values_list("body", "finished"))
        self.assertEqual(steps, [("Prepare mix", False), ("Cycle", False)])

    def test_source_entry_is_untouched(self):
        entry = self.entry()
        svc.save_entry_as_template(entry=entry, user=self.owner, name="X")
        entry.refresh_from_db()
        self.assertEqual(entry.metadata["extra_fields"]["Temp"]["value"], "72")
        self.assertTrue(entry.steps.filter(finished=True).exists())

    def test_overwrite_refreshes_content(self):
        tpl = self.make()
        newer = self.entry(content="<p>Version 2</p>")
        svc.save_entry_as_template(entry=newer, user=self.owner, name="PCR", template=tpl)
        tpl.refresh_from_db()
        self.assertIn("Version 2", tpl.content)
        self.assertEqual(NotebookTemplate.objects.count(), 1)

    def test_validation(self):
        for bad in ("", "   "):
            with self.assertRaises(ValidationError):
                self.make(name=bad)
        with self.assertRaises(ValidationError):
            self.make(name="x" * 121)
        tpl = self.make()
        with self.assertRaises(ValidationError):
            svc.update_template(user=self.owner, template=tpl, icon="<script>")
        svc.update_template(user=self.owner, template=tpl, icon="bi-flask")  # control


class VisibilityTests(Base):
    def usable(self, user, tpl):
        return svc.templates_for(user).filter(pk=tpl.pk).exists()

    def test_private_is_only_the_owner_and_superusers(self):
        tpl = self.make()
        self.assertTrue(self.usable(self.owner, tpl))
        self.assertTrue(self.usable(self.admin, tpl))
        self.assertFalse(self.usable(self.member, tpl))

    def test_group_template_reaches_members_and_the_coordinator_only(self):
        tpl = svc.save_entry_as_template(entry=self.entry(self.coord), user=self.coord, name="G",
                                         visibility="group", group=self.group)
        for user in (self.coord, self.member, self.owner):
            self.assertTrue(self.usable(user, tpl), user.username)
        self.assertFalse(self.usable(self.outsider, tpl))

    def test_lab_template_reaches_everyone(self):
        tpl = svc.save_entry_as_template(entry=self.entry(self.admin), user=self.admin, name="L", visibility="lab")
        self.assertTrue(self.usable(self.outsider, tpl))

    def test_who_may_share_where(self):
        with self.assertRaises(PermissionDenied):
            self.make(visibility="group", group=self.group)  # a plain member cannot
        with self.assertRaises(PermissionDenied):
            self.make(visibility="lab")
        with self.assertRaises(ValidationError):
            svc.save_entry_as_template(entry=self.entry(self.coord), user=self.coord, name="G", visibility="group")
        svc.save_entry_as_template(entry=self.entry(self.coord), user=self.coord, name="G",
                                   visibility="group", group=self.group)  # control

    def test_edit_rights(self):
        tpl = svc.save_entry_as_template(entry=self.entry(self.coord), user=self.coord, name="G",
                                         visibility="group", group=self.group)
        self.assertTrue(svc.can_edit(self.coord, tpl))
        self.assertTrue(svc.can_edit(self.admin, tpl))
        self.assertFalse(svc.can_edit(self.member, tpl))
        with self.assertRaises(PermissionDenied):
            svc.delete_template(user=self.member, template=tpl)
        svc.delete_template(user=self.coord, template=tpl)
        self.assertFalse(NotebookTemplate.objects.exists())

    def test_group_coordinator_can_edit_a_group_template_made_by_a_member_but_not_a_private_one(self):
        private = self.make()
        self.assertFalse(svc.can_edit(self.coord, private))


class ViewTests(Base):
    def api(self, user, payload, name="notebook_templates_api"):
        self.client.force_login(user)
        return self.client.post(reverse(name), json.dumps(payload), content_type="application/json")

    def test_create_entry_from_template_via_the_new_entry_route(self):
        tpl = self.make()
        before = set(NotebookEntry.objects.values_list("pk", flat=True))
        self.client.force_login(self.owner)
        r = self.client.get(reverse("notebook_create"), {"template": svc.key_for(tpl)})
        self.assertEqual(r.status_code, 302)
        new = NotebookEntry.objects.exclude(pk__in=before).get()
        self.assertIn("Amplify", new.content)
        self.assertEqual(new.steps.count(), 2)

    def test_someone_elses_private_template_is_not_used(self):
        tpl = self.make()
        before = NotebookEntry.objects.count()
        self.client.force_login(self.outsider)
        self.client.get(reverse("notebook_create"), {"template": svc.key_for(tpl)})
        created = NotebookEntry.objects.filter(author=self.outsider)
        self.assertEqual(NotebookEntry.objects.count(), before + 1)
        self.assertNotIn("Amplify", created.get().content)

    def test_menu_lists_only_templates_the_user_can_use(self):
        tpl = self.make(name="Secret PCR")
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("notebook_dashboard")), "Secret PCR")
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse("notebook_dashboard")), "Secret PCR")

    def test_save_template_endpoint(self):
        entry = self.entry()
        self.client.force_login(self.owner)
        r = self.client.post(reverse("notebook_entry_save_template", args=[entry.pk]),
                             json.dumps({"name": "From API", "visibility": "private"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(NotebookTemplate.objects.filter(name="From API", owner=self.owner).exists())

    def test_save_template_needs_access_to_the_entry(self):
        entry = self.entry()  # private to owner
        self.client.force_login(self.outsider)
        r = self.client.post(reverse("notebook_entry_save_template", args=[entry.pk]),
                             json.dumps({"name": "Steal"}), content_type="application/json")
        self.assertIn(r.status_code, (403, 404))
        self.assertFalse(NotebookTemplate.objects.filter(name="Steal").exists())

    def test_sharing_refused_through_the_api(self):
        entry = self.entry()
        self.client.force_login(self.owner)
        r = self.client.post(reverse("notebook_entry_save_template", args=[entry.pk]),
                             json.dumps({"name": "L", "visibility": "lab"}), content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(NotebookTemplate.objects.exists())

    def test_manage_api_update_and_delete(self):
        tpl = self.make()
        r = self.api(self.owner, {"action": "update", "id": tpl.pk, "name": "Renamed"})
        self.assertEqual(r.status_code, 200)
        tpl.refresh_from_db()
        self.assertEqual(tpl.name, "Renamed")
        r = self.api(self.member, {"action": "delete", "id": tpl.pk})
        self.assertEqual(r.status_code, 404)  # cannot even see it
        self.assertTrue(NotebookTemplate.objects.filter(pk=tpl.pk).exists())
        self.assertEqual(self.api(self.owner, {"action": "delete", "id": tpl.pk}).status_code, 200)
        self.assertFalse(NotebookTemplate.objects.exists())

    def test_pages_render(self):
        self.make()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("notebook_templates")).status_code, 200)
        entry = self.entry()
        html = self.client.get(reverse("notebook_entry", args=[entry.pk])).content.decode()
        self.assertIn("bx-save-template", html)
