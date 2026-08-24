from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ResourceAccessGrant(models.Model):
    """An auditable explicit grant for a single application resource."""

    class AccessLevel(models.TextChoices):
        VIEW = "view", "View"
        EDIT = "edit", "Edit"
        MANAGE = "manage", "Manage"

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
    )
    object_id = models.CharField(
        max_length=255,
    )
    content_object = GenericForeignKey(
        "content_type",
        "object_id",
        for_concrete_model=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resource_access_grants",
        blank=True,
        null=True,
    )
    research_group = models.ForeignKey(
        "core.ResearchGroup",
        on_delete=models.CASCADE,
        related_name="resource_access_grants",
        blank=True,
        null=True,
    )

    access_level = models.CharField(
        max_length=12,
        choices=AccessLevel.choices,
        default=AccessLevel.VIEW,
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="resource_access_grants_created",
        blank=True,
        null=True,
    )
    granted_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )
    expires_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    revoked_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="resource_access_grants_revoked",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = (
            "content_type_id",
            "object_id",
            "id",
        )
        indexes = (
            models.Index(
                fields=(
                    "content_type",
                    "object_id",
                ),
                name="core_resgrant_target_idx",
            ),
            models.Index(
                fields=(
                    "expires_at",
                    "revoked_at",
                ),
                name="core_resgrant_expiry_idx",
            ),
        )
        constraints = (
            models.CheckConstraint(
                condition=(
                    Q(
                        user__isnull=False,
                        research_group__isnull=True,
                    )
                    | Q(
                        user__isnull=True,
                        research_group__isnull=False,
                    )
                ),
                name="resource_grant_one_principal",
            ),
            models.CheckConstraint(
                condition=Q(
                    access_level__in=(
                        "view",
                        "edit",
                        "manage",
                    )
                ),
                name="resource_grant_valid_access",
            ),
            models.CheckConstraint(
                condition=(
                    Q(revoked_by__isnull=True)
                    | Q(revoked_at__isnull=False)
                ),
                name="resource_grant_revoker_time",
            ),
            models.UniqueConstraint(
                fields=(
                    "content_type",
                    "object_id",
                    "user",
                ),
                condition=Q(
                    user__isnull=False,
                    revoked_at__isnull=True,
                ),
                name="resource_grant_active_user_uniq",
            ),
            models.UniqueConstraint(
                fields=(
                    "content_type",
                    "object_id",
                    "research_group",
                ),
                condition=Q(
                    research_group__isnull=False,
                    revoked_at__isnull=True,
                ),
                name="resource_grant_active_group_uniq",
            ),
        )

    def __str__(self):
        return (
            f"{self.content_type_id}:{self.object_id} "
            f"-> {self.principal_label} ({self.access_level})"
        )

    @property
    def principal_label(self):
        if self.user_id:
            return self.user.get_username()

        if self.research_group_id:
            return self.research_group.name

        return "unassigned"

    @property
    def is_active(self):
        if self.revoked_at is not None:
            return False

        return (
            self.expires_at is None
            or self.expires_at > timezone.now()
        )

    def clean(self):
        super().clean()

        if bool(self.user_id) == bool(self.research_group_id):
            raise ValidationError(
                "Select exactly one grant principal: user or research group."
            )

        if not str(self.object_id).strip():
            raise ValidationError(
                {
                    "object_id":
                    "A resource object identifier is required."
                }
            )

        if self.revoked_by_id and self.revoked_at is None:
            raise ValidationError(
                {
                    "revoked_at":
                    "A revocation timestamp is required."
                }
            )
