"""Activity history: one row per thing added, changed or removed in the lab.

Rows are written by signal handlers (services/activity.py), so every screen and
API is covered without touching each view. Frequent saves of the same record by
the same person are folded into one row (``count``) so autosave does not flood
the history.
"""

from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    class Verb(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_logs",
    )
    # Kept as text so the history survives the user being removed.
    actor_name = models.CharField(max_length=150, blank=True)
    verb = models.CharField(max_length=16, choices=Verb.choices)
    entity_type = models.CharField(max_length=48)
    entity_id = models.BigIntegerField(null=True, blank=True)
    entity_label = models.CharField(max_length=255, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    url = models.CharField(max_length=300, blank=True)
    count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "Activity"
        verbose_name_plural = "Activity history"
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["actor", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.actor_name or '?'} {self.verb} {self.entity_type} {self.entity_label}"
