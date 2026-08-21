from django.conf import settings
from django.db import models
from django.utils import timezone

from .sample import Sample


class SampleAccessGrant(models.Model):
    """
    Direct user-level access to a Sample.

    Direct grants are independent from Sample ownership, Research Groups,
    Collections and Biobanks. Files remain physically stored under the
    Sample owner's protected data root.
    """

    ACCESS_VIEW = "view"
    ACCESS_EDIT = "edit"

    ACCESS_LEVELS = [
        (
            ACCESS_VIEW,
            "View",
        ),
        (
            ACCESS_EDIT,
            "Edit",
        ),
    ]

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sample_access_grants",
    )

    access_level = models.CharField(
        max_length=16,
        choices=ACCESS_LEVELS,
        default=ACCESS_VIEW,
    )

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sample_access_grants_created",
    )

    granted_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Optional expiration time. "
            "Leave blank for access without an expiration date."
        ),
    )

    class Meta:
        ordering = [
            "sample_id",
            "user__username",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sample",
                    "user",
                ],
                name=(
                    "uniq_sample_access_grant_user"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "access_level",
                ],
                name=(
                    "sample_access_user_level_idx"
                ),
            ),
            models.Index(
                fields=[
                    "sample",
                    "expires_at",
                ],
                name=(
                    "sample_access_expiry_idx"
                ),
            ),
        ]

        verbose_name = (
            "Sample Access Grant"
        )

        verbose_name_plural = (
            "Sample Access Grants"
        )

    @property
    def is_expired(self):
        return bool(
            self.expires_at
            and self.expires_at
            <= timezone.now()
        )

    @property
    def is_active(self):
        return not self.is_expired

    def __str__(self):
        return (
            f"{self.sample.sample_id} -> "
            f"{self.user.username} "
            f"({self.get_access_level_display()})"
        )
