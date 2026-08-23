from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """Scientific identity metadata attached to a PAM-backed user."""

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        MEMBERS = "members", "Authenticated members"
        PUBLIC = "public", "Public"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    preferred_name = models.CharField(max_length=150, blank=True)
    institution = models.CharField(max_length=255, blank=True)
    department = models.CharField(
        "department or laboratory",
        max_length=255,
        blank=True,
    )
    orcid = models.CharField("ORCID", max_length=19, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    expertise = models.TextField(blank=True)
    biography = models.TextField(blank=True)
    profile_visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.MEMBERS,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "user profile"
        verbose_name_plural = "user profiles"

    def __str__(self):
        return self.preferred_name or self.user.get_full_name() or self.user.username
