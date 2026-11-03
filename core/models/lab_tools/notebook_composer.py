"""Composable structure of a Notebook entry (B3 Bench step 1.A).

Mirrors the parts of an eLabFTW entry that a researcher assembles
around the main text:

- tags and a custom ID (NotebookTag, NotebookEntry.custom_id);
- custom fields, stored in NotebookEntry.metadata using eLabFTW's own
  JSON layout ({"extra_fields": {...}, "elabftw": {"extra_fields_groups": [...]}}),
  so an .eln export can carry them unchanged;
- steps with completion and deadlines (NotebookStep);
- links between entries (NotebookEntryLink).
"""

from django.conf import settings
from django.db import models


class NotebookTag(models.Model):
    name = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class NotebookStep(models.Model):
    entry = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.CASCADE,
        related_name="steps",
    )
    body = models.CharField(max_length=500)
    position = models.PositiveIntegerField(default=0)
    finished = models.BooleanField(default=False)
    finished_at = models.DateTimeField(null=True, blank=True)
    finished_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.entry_id} step {self.position}: {self.body[:40]}"


class NotebookEntryLink(models.Model):
    """A directed link from one entry to another ("related experiment")."""

    entry = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.CASCADE,
        related_name="entry_links",
    )
    target = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.CASCADE,
        related_name="linked_from",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "target"],
                name="core_nb_entry_link_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(entry=models.F("target")),
                name="core_nb_entry_link_not_self",
            ),
        ]

    def __str__(self):
        return f"{self.entry_id} -> {self.target_id}"
