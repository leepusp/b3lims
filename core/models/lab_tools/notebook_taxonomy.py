"""Statuses and categories for Notebook entries, per research group (B3 Bench 2.2).

Behaviour studied from eLabFTW (team statuses and categories with colours) and
reimplemented here; no eLabFTW code is used.

A scope is one research group, or the whole lab when ``research_group`` is empty.
An entry uses the list of its own research group; with none, the lab list.
"""

from django.db import models
from django.db.models import Q


class NotebookStatus(models.Model):
    class Kind(models.TextChoices):
        DRAFT = "draft", "Not started"
        ACTIVE = "active", "In progress"
        DONE = "done", "Done, waiting for review"
        REVIEWED = "reviewed", "Reviewed"
        ARCHIVED = "archived", "Archived"

    # Slugs are unique across the whole lab, so an entry's ``status`` text always
    # identifies one row, even if the entry later moves to another group.
    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    color = models.CharField(max_length=7, default="#6b7280")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ACTIVE)
    position = models.PositiveIntegerField(default=0)
    research_group = models.ForeignKey(
        "core.ResearchGroup",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notebook_statuses",
    )

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Notebook status"
        verbose_name_plural = "Notebook statuses"
        constraints = [
            models.UniqueConstraint(
                fields=["research_group", "name"],
                condition=Q(research_group__isnull=False),
                name="nbstatus_group_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(research_group__isnull=True),
                name="nbstatus_lab_name_uniq",
            ),
        ]

    def __str__(self):
        return self.name


class NotebookCategory(models.Model):
    name = models.CharField(max_length=64)
    color = models.CharField(max_length=7, default="#6b7280")
    position = models.PositiveIntegerField(default=0)
    research_group = models.ForeignKey(
        "core.ResearchGroup",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notebook_categories",
    )

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Notebook category"
        verbose_name_plural = "Notebook categories"
        constraints = [
            models.UniqueConstraint(
                fields=["research_group", "name"],
                condition=Q(research_group__isnull=False),
                name="nbcategory_group_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(research_group__isnull=True),
                name="nbcategory_lab_name_uniq",
            ),
        ]

    def __str__(self):
        return self.name
