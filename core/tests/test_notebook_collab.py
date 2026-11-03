"""Step 2.1: revisions, exclusive edit, comments, file versions, todolist."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models.lab_tools.notebook import NotebookAttachment, NotebookEntry
from core.models.lab_tools.notebook_collab import NotebookEditLock, NotebookRevision, NotebookTodo
from core.services import notebook_collab as collab


def post(client, url, data, **extra):
    return client.post(url, data=json.dumps(data), content_type="application/json", **extra)


@override_settings(FORCE_SCRIPT_NAME=None)
class CollabBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("owner", password="x")
        cls.other = User.objects.create_user("other", password="x")
        cls.entry = NotebookEntry.objects.create(
            title="Collab", author=cls.owner, content="<p>one</p>", visibility="private"
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.update = reverse("notebook_entry_update_api", args=[self.entry.pk])


class RevisionTests(CollabBase):
    def test_first_edit_keeps_a_baseline(self):
        post(self.client, self.update, {"content": "<p>two</p>"})
        contents = list(self.entry.revisions.order_by("id").values_list("content", flat=True))
        self.assertEqual(contents, ["<p>one</p>", "<p>two</p>"])

    def test_quick_saves_by_the_same_author_are_coalesced(self):
        post(self.client, self.update, {"content": "<p>two</p>"})
        post(self.client, self.update, {"content": "<p>three</p>"})
        post(self.client, self.update, {"content": "<p>four</p>"})
        self.assertEqual(self.entry.revisions.count(), 2)  # baseline + one coalesced revision
        self.assertEqual(self.entry.revisions.first().content, "<p>four</p>")

    def test_old_revision_is_not_overwritten_after_the_window(self):
        post(self.client, self.update, {"content": "<p>two</p>"})
        NotebookRevision.objects.filter(entry=self.entry).update(updated_at=timezone.now() - timedelta(hours=1))
        post(self.client, self.update, {"content": "<p>three</p>"})
        self.assertEqual(self.entry.revisions.count(), 3)

    def test_unchanged_content_adds_nothing(self):
        post(self.client, self.update, {"content": "<p>one</p>"})
        self.assertEqual(self.entry.revisions.count(), 0)

    def test_title_only_change_adds_nothing(self):
        post(self.client, self.update, {"title": "New title"})
        self.assertEqual(self.entry.revisions.count(), 0)

    def test_list_and_diff(self):
        post(self.client, self.update, {"content": "<p>one</p><p>two</p>"})
        first = self.entry.revisions.order_by("id").first()
        url = reverse("notebook_revisions_api", args=[self.entry.pk])
        listed = self.client.get(url).json()["revisions"]
        self.assertEqual(len(listed), 2)
        diff = self.client.get(url, {"id": first.pk}).json()["diff"]
        self.assertIn({"type": "add", "text": "two"}, diff)
        self.assertIn({"type": "same", "text": "one"}, diff)

    def test_restore_brings_back_text_and_keeps_history(self):
        post(self.client, self.update, {"content": "<p>two</p>"})
        baseline = self.entry.revisions.order_by("id").first()
        response = post(self.client, reverse("notebook_revisions_api", args=[self.entry.pk]), {"revision_id": baseline.pk})
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "<p>one</p>")
        self.assertGreaterEqual(self.entry.revisions.count(), 2)

    def test_restore_sanitises_old_content(self):
        rev = NotebookRevision.objects.create(entry=self.entry, content='<p>x</p><img src=x onerror="alert(1)">')
        post(self.client, reverse("notebook_revisions_api", args=[self.entry.pk]), {"revision_id": rev.pk})
        self.entry.refresh_from_db()
        self.assertNotIn("onerror", self.entry.content)

    def test_other_users_entry_is_not_readable_or_restorable(self):
        self.client.force_login(self.other)
        url = reverse("notebook_revisions_api", args=[self.entry.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertIn(post(self.client, url, {"revision_id": 1}).status_code, (403, 404))

    def test_revision_cap(self):
        old = collab.MAX_REVISIONS
        collab.MAX_REVISIONS = 3
        try:
            for i in range(8):
                NotebookRevision.objects.filter(entry=self.entry).update(updated_at=timezone.now() - timedelta(hours=1))
                post(self.client, self.update, {"content": f"<p>v{i}</p>"})
        finally:
            collab.MAX_REVISIONS = old
        self.assertLessEqual(self.entry.revisions.count(), 3)

    def test_diff_collapses_long_unchanged_runs(self):
        same = "".join(f"<p>line {i}</p>" for i in range(30))
        rows = collab.diff_content(same + "<p>a</p>", same + "<p>b</p>")
        self.assertTrue(any(r["type"] == "skip" for r in rows))
        self.assertLess(len(rows), 15)


class LockTests(CollabBase):
    def lock(self, action, token, **extra):
        return post(self.client, reverse("notebook_lock_api", args=[self.entry.pk]), {"action": action, "token": token, **extra})

    def test_acquire_then_second_tab_is_refused(self):
        self.assertTrue(self.lock("acquire", "tab-a").json()["granted"])
        refused = self.lock("acquire", "tab-b").json()
        self.assertFalse(refused["granted"])
        self.assertEqual(refused["holder"], "owner")

    def test_takeover_and_old_tab_cannot_save(self):
        self.lock("acquire", "tab-a")
        self.assertTrue(self.lock("acquire", "tab-b", force=True).json()["granted"])
        stale = post(self.client, self.update, {"content": "<p>late</p>"}, HTTP_X_LOCK_TOKEN="tab-a")
        self.assertEqual(stale.status_code, 423)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "<p>one</p>")
        fresh = post(self.client, self.update, {"content": "<p>ok</p>"}, HTTP_X_LOCK_TOKEN="tab-b")
        self.assertEqual(fresh.status_code, 200)

    def test_write_without_token_is_refused_while_locked(self):
        self.lock("acquire", "tab-a")
        self.assertEqual(post(self.client, self.update, {"title": "x"}).status_code, 423)

    def test_expired_lock_is_free(self):
        self.lock("acquire", "tab-a")
        NotebookEditLock.objects.update(heartbeat_at=timezone.now() - timedelta(minutes=5))
        self.assertTrue(self.lock("acquire", "tab-b").json()["granted"])
        self.assertEqual(post(self.client, self.update, {"title": "x"}, HTTP_X_LOCK_TOKEN="tab-b").status_code, 200)

    def test_heartbeat_reports_takeover(self):
        self.lock("acquire", "tab-a")
        self.assertTrue(self.lock("heartbeat", "tab-a").json()["granted"])
        self.lock("acquire", "tab-b", force=True)
        self.assertFalse(self.lock("heartbeat", "tab-a").json()["granted"])

    def test_release_frees_the_entry(self):
        self.lock("acquire", "tab-a")
        self.lock("release", "tab-a")
        self.assertEqual(post(self.client, self.update, {"title": "x"}).status_code, 200)

    def test_release_with_wrong_token_does_nothing(self):
        self.lock("acquire", "tab-a")
        self.lock("release", "nope")
        self.assertEqual(NotebookEditLock.objects.count(), 1)

    def test_spreadsheets_respect_the_lock(self):
        self.lock("acquire", "tab-a")
        blocked = post(self.client, reverse("notebook_spreadsheets_api", args=[self.entry.pk]), {"action": "add"})
        self.assertEqual(blocked.status_code, 423)

    def test_missing_token_is_rejected(self):
        self.assertEqual(self.lock("acquire", "").status_code, 400)

    def test_viewer_cannot_lock(self):
        NotebookEntry.objects.filter(pk=self.entry.pk).update(visibility="lab")
        self.client.force_login(self.other)
        self.assertIn(self.lock("acquire", "x").status_code, (403, 404))


class CommentTests(CollabBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("notebook_comments_api", args=[self.entry.pk])

    def test_add_edit_delete(self):
        rows = post(self.client, self.url, {"action": "add", "body": "Looks good <b>"}).json()["comments"]
        self.assertEqual(rows[0]["body"], "Looks good <b>")  # stored as typed; the page escapes it
        cid = rows[0]["id"]
        rows = post(self.client, self.url, {"action": "edit", "id": cid, "body": "Edited"}).json()["comments"]
        self.assertTrue(rows[0]["edited"])
        rows = post(self.client, self.url, {"action": "delete", "id": cid}).json()["comments"]
        self.assertEqual(rows, [])

    def test_empty_and_huge_comments_refused(self):
        self.assertEqual(post(self.client, self.url, {"action": "add", "body": "  "}).status_code, 400)
        self.assertEqual(post(self.client, self.url, {"action": "add", "body": "x" * 6000}).status_code, 400)

    def test_only_author_edits_but_owner_can_delete(self):
        NotebookEntry.objects.filter(pk=self.entry.pk).update(visibility="lab")
        self.client.force_login(self.other)
        cid = post(self.client, self.url, {"action": "add", "body": "from other"}).json()["comments"][0]["id"]
        self.client.force_login(self.owner)
        self.assertEqual(post(self.client, self.url, {"action": "edit", "id": cid, "body": "hijack"}).status_code, 403)
        self.assertEqual(post(self.client, self.url, {"action": "delete", "id": cid}).json()["comments"], [])

    def test_stranger_cannot_comment_on_private_entry(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(post(self.client, self.url, {"action": "add", "body": "hi"}).status_code, 404)


class FileTests(CollabBase):
    def setUp(self):
        super().setUp()
        import tempfile

        from django.core.files.storage import FileSystemStorage

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        field = NotebookAttachment._meta.get_field("file")
        original = field.storage
        field.storage = FileSystemStorage(location=tmp.name)
        self.addCleanup(setattr, field, "storage", original)

    def upload(self, name=b"v1 data", filename="data.csv"):
        url = reverse("notebook_upload_attachment_api", args=[self.entry.pk])
        return self.client.post(url, {"file": SimpleUploadedFile(filename, name), "caption": filename})

    def test_entry_page_renders_with_files(self):
        """Regression: an entry with attachments used to return 500."""
        self.upload()
        page = self.client.get(reverse("notebook_entry", args=[self.entry.pk]))
        self.assertEqual(page.status_code, 200)
        files = self.client.get(reverse("notebook_entry_files_api", args=[self.entry.pk])).json()["attachments"]
        self.assertEqual(files[0]["name"], "data.csv")

    def test_replace_creates_a_new_version_and_keeps_the_old(self):
        self.upload()
        first = NotebookAttachment.objects.get()
        response = self.client.post(
            reverse("notebook_file_replace_api", args=[self.entry.pk]),
            {"attachment_id": first.pk, "file": SimpleUploadedFile("data.csv", b"v2 data")},
        )
        self.assertEqual(response.json()["version"], 2)
        first.refresh_from_db()
        self.assertFalse(first.is_current)
        files = self.client.get(reverse("notebook_entry_files_api", args=[self.entry.pk])).json()["attachments"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["version"], 2)
        self.assertEqual([h["version"] for h in files[0]["history"]], [1])
        self.assertNotEqual(NotebookAttachment.objects.get(version=2).checksum_sha256, first.checksum_sha256)

    def test_cannot_replace_a_superseded_version_or_foreign_file(self):
        self.upload()
        first = NotebookAttachment.objects.get()
        url = reverse("notebook_file_replace_api", args=[self.entry.pk])
        self.client.post(url, {"attachment_id": first.pk, "file": SimpleUploadedFile("a", b"2")})
        again = self.client.post(url, {"attachment_id": first.pk, "file": SimpleUploadedFile("a", b"3")})
        self.assertEqual(again.status_code, 404)

    def test_caption_edit(self):
        self.upload()
        att = NotebookAttachment.objects.get()
        out = post(self.client, reverse("notebook_file_caption_api", args=[self.entry.pk]), {"attachment_id": att.pk, "caption": "Gel image"})
        self.assertEqual(out.json()["caption"], "Gel image")

    def test_non_owner_cannot_replace(self):
        self.upload()
        att = NotebookAttachment.objects.get()
        self.client.force_login(self.other)
        out = self.client.post(
            reverse("notebook_file_replace_api", args=[self.entry.pk]),
            {"attachment_id": att.pk, "file": SimpleUploadedFile("a", b"x")},
        )
        self.assertIn(out.status_code, (403, 404))


class TodoTests(CollabBase):
    url = None

    def setUp(self):
        super().setUp()
        self.url = reverse("notebook_todos_api")

    def test_add_toggle_delete_are_per_user(self):
        rows = post(self.client, self.url, {"action": "add", "text": "Order primers", "entry_id": self.entry.pk}).json()["todos"]
        self.assertEqual(rows[0]["entry_id"], self.entry.pk)
        tid = rows[0]["id"]
        self.assertTrue(post(self.client, self.url, {"action": "toggle", "id": tid}).json()["todos"][0]["done"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).json()["todos"], [])
        self.assertEqual(post(self.client, self.url, {"action": "delete", "id": tid}).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(post(self.client, self.url, {"action": "delete", "id": tid}).json()["todos"], [])

    def test_cannot_attach_a_task_to_an_invisible_entry(self):
        self.client.force_login(self.other)
        self.assertEqual(post(self.client, self.url, {"action": "add", "text": "x", "entry_id": self.entry.pk}).status_code, 404)

    def test_clear_done(self):
        NotebookTodo.objects.create(user=self.owner, text="a", done=True)
        NotebookTodo.objects.create(user=self.owner, text="b")
        rows = post(self.client, self.url, {"action": "clear_done"}).json()["todos"]
        self.assertEqual([r["text"] for r in rows], ["b"])


class PageWiringTests(CollabBase):
    """The pages expose the 2.1 controls and hand their URLs to the script."""

    def test_entry_page_has_comments_revisions_and_lock_urls(self):
        page = self.client.get(reverse("notebook_entry", args=[self.entry.pk]))
        self.assertContains(page, 'id="bx-revisions"')
        self.assertContains(page, 'data-pane="comments"')
        self.assertContains(page, 'id="bx-lock-banner"')
        urls = page.context["page_state"]["urls"]
        for key in ("revisions", "comments", "lock", "replace", "file_caption"):
            self.assertIn(key, urls)

    def test_viewer_does_not_get_restore_or_replace_controls(self):
        NotebookEntry.objects.filter(pk=self.entry.pk).update(visibility="lab")
        self.client.force_login(self.other)
        page = self.client.get(reverse("notebook_entry", args=[self.entry.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="bx-rev-restore"')
        self.assertFalse(page.context["page_state"]["can_edit"])

    def test_dashboard_shows_todo_panel(self):
        page = self.client.get(reverse("notebook_dashboard"))
        self.assertContains(page, 'id="eln-todo"')
        self.assertContains(page, reverse("notebook_todos_api"))
