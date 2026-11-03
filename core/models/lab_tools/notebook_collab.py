"""Collaboration and history for Notebook entries (B3 Bench step 2.1).

Behaviour studied from eLabFTW (revisions, comments, exclusive edit mode,
todolist) and reimplemented here; no eLabFTW code is used.
"""

from django.conf import settings
from django.db import models


class NotebookRevision(models.Model):
    """A saved version of an entry's text, for compare and restore."""

    entry = models.ForeignKey("core.NotebookEntry", on_delete=models.CASCADE, related_name="revisions")
    title = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["entry", "-id"], name="core_nbrev_entry_idx")]

    def __str__(self):
        return f"{self.entry_id} rev {self.pk}"


class NotebookComment(models.Model):
    entry = models.ForeignKey("core.NotebookEntry", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]


class NotebookEditLock(models.Model):
    """Exclusive edit mode: one browser tab edits an entry at a time.

    The holder renews ``heartbeat_at`` while the page is open; a lock whose
    heartbeat is older than the TTL is free to take.
    """

    entry = models.OneToOneField("core.NotebookEntry", on_delete=models.CASCADE, related_name="edit_lock")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    token = models.CharField(max_length=64)
    acquired_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField()


class NotebookTodo(models.Model):
    """Personal to-do list (eLabFTW todolist), optionally tied to an entry."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notebook_todos")
    entry = models.ForeignKey(
        "core.NotebookEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="todos"
    )
    text = models.CharField(max_length=255)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["done", "id"]
