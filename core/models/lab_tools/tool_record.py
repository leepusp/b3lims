"""Independent Lab Tools records (Gel, Plasmid assembly, Chemical, ...).

Each record belongs to one tool type. The metadata and the small JSON state
of every window live in PostgreSQL; the files (a gel photo, a structure
drawing, ...) live in the owner's protected ``biobank`` home directory, in a
folder named after the tool: ``users/<username>/tools/<tool>/<id>/``.
"""

import re
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.services.lab_tools_storage import (
    lab_tools_storage,
    validate_username,
)


def tool_record_upload_to(instance, filename):
    if not instance.pk or not instance.owner_id:
        raise ValueError("A tool file requires a saved record with an owner.")

    username = validate_username(instance.owner.get_username())
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name).strip("._")
    safe = (safe or "file")[:120]

    return (
        f"users/{username}/tools/{instance.tool}/{instance.pk}/"
        f"{uuid.uuid4().hex}_{safe}"
    )


class ToolRecord(models.Model):
    TOOL_CHOICES = [
        ("gel", "Gel"),
        ("assembly", "Plasmid assembly"),
        ("chemical", "Chemical"),
        ("rnafold", "RNA workbench"),
        ("protein3d", "Protein workbench"),
    ]
    # RNA and Protein are registry types (one item each). The two workbench
    # tool types stay readable for records already created, but are no longer
    # offered when creating or filtering.
    CREATABLE_TOOLS = ("gel", "assembly", "chemical")
    CREATABLE_CHOICES = [TOOL_CHOICES[0], TOOL_CHOICES[1], TOOL_CHOICES[2]]

    tool = models.CharField(max_length=32, choices=TOOL_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tool_records",
    )
    # State of every window of this record: {"gel": {...}, "assembly": {...}}.
    data = models.JSONField(default=dict, blank=True)
    file = models.FileField(
        upload_to=tool_record_upload_to,
        storage=lab_tools_storage,
        max_length=512,
        blank=True,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["tool", "owner"])]

    def __str__(self):
        return f"{self.name} ({self.tool})"


@receiver(post_delete, sender=ToolRecord)
def delete_tool_record_file(sender, instance, **kwargs):
    if instance.file and instance.file.name:
        instance.file.storage.delete(instance.file.name)
