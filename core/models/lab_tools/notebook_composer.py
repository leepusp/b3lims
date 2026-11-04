"""Composable structure of a Notebook entry (B3 Bench step 1.A).

Mirrors the parts of an eLabFTW entry that a researcher assembles
around the main text:

- tags and keywords from the biobank-wide vocabulary (core.Tag,
  core.KeywordValue; NotebookTag is the legacy list kept for rollback)
  and a custom ID (NotebookEntry.custom_id);
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


class NotebookFavoriteTag(models.Model):
    """A tag a user keeps one click away in the entry editor."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notebook_favorite_tags",
    )
    # The biobank-wide vocabulary (core.Tag), shared with samples,
    # collections and biobanks, not a notebook-only list.
    tag = models.ForeignKey(
        "core.Tag",
        on_delete=models.CASCADE,
        related_name="notebook_favorites",
    )
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "tag"], name="core_nb_favtag_unique"),
        ]

    def __str__(self):
        return f"{self.user_id} favourite {self.tag_id}"


class NotebookStep(models.Model):
    entry = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.CASCADE,
        related_name="steps",
    )
    body = models.CharField(max_length=500)
    # Optional heading the step is listed under ("Preparation", "Imaging").
    # db_default keeps inserts from an older release valid during cutover.
    group = models.CharField(max_length=80, blank=True, default="", db_default="")
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


class NotebookPin(models.Model):
    """An entry pinned by one user at the top of their ELN dashboard."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notebook_pins",
    )
    entry = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.CASCADE,
        related_name="pins",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "entry"], name="core_nb_pin_unique"),
        ]


class NotebookSpreadsheet(models.Model):
    """A spreadsheet with formulas inside an entry (eLabFTW spreadsheet editor).

    ``data`` keeps the raw cell values as typed, so formulas such as
    ``=B3*B1`` are stored as text and evaluated in the browser.
    """

    entry = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.CASCADE,
        related_name="spreadsheets",
    )
    title = models.CharField(max_length=120, default="Table")
    data = models.JSONField(default=list, blank=True)
    column_widths = models.JSONField(default=list, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.entry_id}: {self.title}"
