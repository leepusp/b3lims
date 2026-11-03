"""Trash, restore, permanent delete and file removal for Notebook entries."""

import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from core.models.lab_tools.notebook import NotebookAttachment, NotebookEntry
from core.models.lab_tools.notebook_collab import NotebookComment, NotebookEditLock


def batch(client, action, ids, **extra):
    return client.post(
        reverse("notebook_dashboard_batch_api"),
        data=json.dumps({"action": action, "ids": ids, **extra}),
        content_type="application/json",
    )


@override_settings(FORCE_SCRIPT_NAME=None)
class TrashBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("owner", password="x")
        cls.other = User.objects.create_user("other", password="x")
        cls.admin = User.objects.create_superuser("admin", "a@b.c", "x")

    def setUp(self):
        self.entry = NotebookEntry.objects.create(title="Gel run", author=self.owner, visibility="lab")
        self.client.force_login(self.owner)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage_root = Path(tmp.name)
        field = NotebookAttachment._meta.get_field("file")
        original = field.storage
        field.storage = FileSystemStorage(location=tmp.name)
        self.addCleanup(setattr, field, "storage", original)


class TrashTests(TrashBase):
    def test_trash_hides_the_entry_everywhere(self):
        self.assertEqual(batch(self.client, "trash", [self.entry.pk]).json()["changed"], 1)
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.deleted_at)
        self.assertEqual(self.entry.deleted_by, self.owner)
        self.assertEqual(self.client.get(reverse("notebook_entry", args=[self.entry.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("notebook_comments_api", args=[self.entry.pk])).status_code, 404)
        listed = self.client.get(reverse("notebook_dashboard")).context["page"]
        self.assertNotIn(self.entry.pk, [e.pk for e in listed])
        # other users no longer see a "lab" entry either
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("notebook_entry", args=[self.entry.pk])).status_code, 404)

    def test_removing_releases_the_edit_lock_so_a_restore_can_be_edited_at_once(self):
        lock = reverse("notebook_lock_api", args=[self.entry.pk])
        acquire = lambda token: self.client.post(  # noqa: E731
            lock, data=json.dumps({"action": "acquire", "token": token}), content_type="application/json"
        )
        self.assertTrue(acquire("tab-a").json()["granted"])
        batch(self.client, "trash", [self.entry.pk])
        self.assertFalse(NotebookEditLock.objects.filter(entry=self.entry).exists())
        batch(self.client, "restore", [self.entry.pk])
        self.assertTrue(acquire("tab-b").json()["granted"])

    def test_trashed_entry_is_not_offered_as_a_link_target(self):
        keeper = NotebookEntry.objects.create(title="Keeper", author=self.owner)
        url = reverse("notebook_lookup_api", args=[keeper.pk])
        before = self.client.get(url, {"kind": "experiments", "q": "Gel"}).json()
        self.assertIn(self.entry.pk, [row["id"] for row in before["results"]])  # control: it is offered
        batch(self.client, "trash", [self.entry.pk])
        after = self.client.get(url, {"kind": "experiments", "q": "Gel"}).json()
        self.assertEqual(after["status"], "success")
        self.assertNotIn(self.entry.pk, [row["id"] for row in after["results"]])

    def test_only_the_owner_can_remove(self):
        self.client.force_login(self.other)
        out = batch(self.client, "trash", [self.entry.pk]).json()
        self.assertEqual((out["changed"], out["skipped"]), (0, 1))
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.deleted_at)

    def test_trash_view_lists_own_removed_entries_with_actions(self):
        batch(self.client, "trash", [self.entry.pk])
        page = self.client.get(reverse("notebook_dashboard"), {"state": "trash"})
        self.assertEqual([e.pk for e in page.context["page"]], [self.entry.pk])
        self.assertContains(page, 'data-action="restore"')
        self.assertContains(page, 'data-action="purge"')
        self.assertNotContains(page, 'data-action="trash"')
        self.assertEqual(page.context["trash_count"], 1)
        self.client.force_login(self.other)
        self.assertEqual(list(self.client.get(reverse("notebook_dashboard"), {"state": "trash"}).context["page"]), [])

    def test_restore_brings_it_back(self):
        batch(self.client, "trash", [self.entry.pk])
        self.assertEqual(batch(self.client, "restore", [self.entry.pk]).json()["changed"], 1)
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.deleted_at)
        self.assertEqual(self.client.get(reverse("notebook_entry", args=[self.entry.pk])).status_code, 200)

    def test_restore_of_an_active_entry_does_nothing(self):
        out = batch(self.client, "restore", [self.entry.pk]).json()
        self.assertEqual((out["changed"], out["skipped"]), (0, 1))

    def test_other_user_cannot_restore_or_purge_someone_elses_trash(self):
        batch(self.client, "trash", [self.entry.pk])
        self.client.force_login(self.other)
        self.assertEqual(batch(self.client, "restore", [self.entry.pk]).json()["changed"], 0)
        self.assertEqual(batch(self.client, "purge", [self.entry.pk]).json()["changed"], 0)
        self.assertTrue(NotebookEntry.objects.filter(pk=self.entry.pk).exists())

    def test_superuser_can_restore_and_purge_anyones(self):
        batch(self.client, "trash", [self.entry.pk])
        self.client.force_login(self.admin)
        self.assertEqual(batch(self.client, "purge", [self.entry.pk]).json()["changed"], 1)
        self.assertFalse(NotebookEntry.objects.filter(pk=self.entry.pk).exists())

    def test_purge_only_touches_entries_already_in_the_trash(self):
        out = batch(self.client, "purge", [self.entry.pk]).json()
        self.assertEqual(out["changed"], 0)
        self.assertTrue(NotebookEntry.objects.filter(pk=self.entry.pk).exists())

    def test_purge_removes_rows_comments_and_stored_files(self):
        upload = reverse("notebook_upload_attachment_api", args=[self.entry.pk])
        self.client.post(upload, {"file": SimpleUploadedFile("gel.png", b"png-bytes"), "caption": "gel"})
        attachment = NotebookAttachment.objects.get()
        stored = Path(attachment.file.path)
        self.assertTrue(stored.exists())
        NotebookComment.objects.create(entry=self.entry, author=self.owner, body="note")
        batch(self.client, "trash", [self.entry.pk])
        out = batch(self.client, "purge", [self.entry.pk]).json()
        self.assertEqual(out["changed"], 1)
        self.assertNotIn("files_left_on_disk", out)
        self.assertFalse(stored.exists())
        self.assertFalse(NotebookAttachment.objects.exists())
        self.assertFalse(NotebookComment.objects.exists())

    def test_purge_survives_a_file_that_cannot_be_removed(self):
        self.client.post(
            reverse("notebook_upload_attachment_api", args=[self.entry.pk]),
            {"file": SimpleUploadedFile("a.txt", b"x"), "caption": "a"},
        )
        batch(self.client, "trash", [self.entry.pk])
        from unittest.mock import patch

        with patch.object(FileSystemStorage, "delete", side_effect=PermissionError("not yours")):
            out = batch(self.client, "purge", [self.entry.pk]).json()
        self.assertEqual(out["changed"], 1)
        self.assertEqual(out["files_left_on_disk"], 1)
        self.assertFalse(NotebookEntry.objects.filter(pk=self.entry.pk).exists())

    def test_entry_page_offers_remove_only_to_the_owner(self):
        self.assertContains(self.client.get(reverse("notebook_entry", args=[self.entry.pk])), 'id="bx-trash"')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("notebook_entry", args=[self.entry.pk])), 'id="bx-trash"')

    def test_old_direct_hard_delete_endpoint_is_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("notebook_delete_entry_api", args=[self.entry.pk])


class FileDeleteTests(TrashBase):
    def upload(self, name="data.csv", body=b"v1"):
        return self.client.post(
            reverse("notebook_upload_attachment_api", args=[self.entry.pk]),
            {"file": SimpleUploadedFile(name, body), "caption": name},
        )

    def delete(self, attachment_id, **extra):
        return self.client.post(
            reverse("notebook_file_delete_api", args=[self.entry.pk]),
            data=json.dumps({"attachment_id": attachment_id}),
            content_type="application/json",
            **extra,
        )

    def test_delete_removes_every_version_and_its_files(self):
        self.upload()
        first = NotebookAttachment.objects.get()
        self.client.post(
            reverse("notebook_file_replace_api", args=[self.entry.pk]),
            {"attachment_id": first.pk, "file": SimpleUploadedFile("data.csv", b"v2")},
        )
        paths = [Path(a.file.path) for a in NotebookAttachment.objects.all()]
        self.assertEqual(len(paths), 2)
        current = NotebookAttachment.objects.get(is_current=True)
        out = self.delete(current.pk).json()
        self.assertEqual(out["removed"], 2)
        self.assertFalse(NotebookAttachment.objects.exists())
        self.assertFalse(any(p.exists() for p in paths))

    def test_superseded_version_cannot_be_deleted_directly(self):
        self.upload()
        first = NotebookAttachment.objects.get()
        self.client.post(
            reverse("notebook_file_replace_api", args=[self.entry.pk]),
            {"attachment_id": first.pk, "file": SimpleUploadedFile("data.csv", b"v2")},
        )
        self.assertEqual(self.delete(first.pk).status_code, 404)
        self.assertEqual(NotebookAttachment.objects.count(), 2)

    def test_only_the_owner_can_delete_a_file(self):
        self.upload()
        attachment = NotebookAttachment.objects.get()
        self.client.force_login(self.other)
        self.assertEqual(self.delete(attachment.pk).status_code, 403)
        self.assertTrue(NotebookAttachment.objects.exists())

    def test_edit_lock_of_another_window_blocks_deleting(self):
        self.upload()
        attachment = NotebookAttachment.objects.get()
        self.client.post(
            reverse("notebook_lock_api", args=[self.entry.pk]),
            data=json.dumps({"action": "acquire", "token": "tab-a"}),
            content_type="application/json",
        )
        self.assertEqual(self.delete(attachment.pk, HTTP_X_LOCK_TOKEN="tab-b").status_code, 423)
        self.assertTrue(NotebookAttachment.objects.exists())


class PrivateDraftsRetiredTests(TestCase):
    def test_old_bookmarks_land_on_the_dashboard(self):
        for path in (
            "/internal/lab-tools/eln-experimental/",
            "/internal/lab-tools/eln-experimental/private/",
            "/internal/lab-tools/eln-experimental/private/new/",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response["Location"].endswith(reverse("notebook_dashboard")), path)

    def test_pages_no_longer_link_to_private_drafts(self):
        User = get_user_model()
        user = User.objects.create_user("p", password="x")
        self.client.force_login(user)
        entry = NotebookEntry.objects.create(title="x", author=user)
        for url in (reverse("notebook_dashboard"), reverse("notebook_entry", args=[entry.pk])):
            self.assertNotContains(self.client.get(url), "Private drafts")


class UploadsReferenceTests(TrashBase):
    """Regression: the "attached file" custom field looked up a field that does not exist."""

    def test_lookup_lists_current_files_by_their_uploaded_name(self):
        upload = reverse("notebook_upload_attachment_api", args=[self.entry.pk])
        self.client.post(upload, {"file": SimpleUploadedFile("gel_image.png", b"1"), "caption": "gel"})
        first = NotebookAttachment.objects.get()
        self.client.post(
            reverse("notebook_file_replace_api", args=[self.entry.pk]),
            {"attachment_id": first.pk, "file": SimpleUploadedFile("gel_image_v2.png", b"2")},
        )
        url = reverse("notebook_lookup_api", args=[self.entry.pk])
        everything = self.client.get(url, {"kind": "uploads"}).json()
        self.assertEqual(everything["status"], "success")
        self.assertEqual([r["label"] for r in everything["results"]], ["gel_image_v2.png"])  # not the old version
        found = self.client.get(url, {"kind": "uploads", "q": "gel_image_v2"}).json()["results"]
        self.assertEqual(len(found), 1)
        self.assertEqual(self.client.get(url, {"kind": "uploads", "q": "nothing-here"}).json()["results"], [])


class DashboardBatchBarTests(TrashBase):
    """The page script needs these elements in every mode; a missing one breaks selection."""

    REQUIRED = ('id="eln-batch"', 'id="eln-sel-count"', 'id="eln-batch-msg"', 'id="eln-all"')

    def test_required_elements_exist_in_normal_and_trash_modes(self):
        batch(self.client, "trash", [NotebookEntry.objects.create(title="gone", author=self.owner).pk])
        for state in ("active", "trash"):
            page = self.client.get(reverse("notebook_dashboard"), {"state": state})
            for marker in self.REQUIRED:
                self.assertContains(page, marker, msg_prefix=f"{state}: ")
