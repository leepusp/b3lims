"""Entry templates saved by users (B3 Bench 2.2).

The built-in templates stay in code; these are the lab's own, made from a real
entry ("Save as template") and shared with nobody, a research group, or the lab.
"""

from django.conf import settings
from django.db import models


class NotebookTemplate(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Only me"
        GROUP = "group", "My research group"
        LAB = "lab", "Whole lab"

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    icon = models.CharField(max_length=40, default="bi-file-earmark-text")
    title = models.CharField(max_length=255, default="Untitled entry")
    entry_type = models.CharField(max_length=32, default="experiment")
    content = models.TextField(blank=True)
    protocol_content = models.TextField(blank=True)
    # {"custom_fields": {...}, "custom_field_groups": [...], "steps": ["..."]}
    # (older rows also carry extra_fields / elabftw.extra_fields_groups, see
    # services/custom_field_layout.py)
    structure = models.JSONField(default=dict, blank=True)

    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE)
    research_group = models.ForeignKey(
        "core.ResearchGroup",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notebook_templates",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notebook_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Notebook template"
        verbose_name_plural = "Notebook templates"

    def __str__(self):
        return self.name
