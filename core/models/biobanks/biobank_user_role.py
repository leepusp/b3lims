from django.db import models
from django.contrib.auth.models import User


class BiobankUserRole(models.Model):
    """
    Defines user roles within a biobank.

    This model provides object-level access control for biobank governance.
    """

    OWNER = "owner"
    MANAGER = "manager"
    EDITOR = "editor"
    VIEWER = "viewer"
    MEMBER = "member"  # Legacy alias kept for compatibility with older records.

    ROLE_CHOICES = [
        (OWNER, "Owner"),
        (MANAGER, "Manager"),
        (EDITOR, "Editor"),
        (VIEWER, "Viewer"),
        (MEMBER, "Member / legacy"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="biobank_roles",
    )

    biobank = models.ForeignKey(
        "core.Biobank",
        on_delete=models.CASCADE,
        related_name="user_roles",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "biobank")
        ordering = ["role", "user__username"]
        verbose_name = "Biobank permission"
        verbose_name_plural = "Biobank permissions"

    def __str__(self):
        return f"{self.user.username} - {self.biobank.name} ({self.role})"
