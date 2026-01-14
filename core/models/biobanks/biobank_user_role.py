from django.db import models
from django.contrib.auth.models import User


class BiobankUserRole(models.Model):
    """
    Define papéis de usuário dentro de um Biobank.
    ACL de governança no nível mais alto.
    """

    OWNER = "owner"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"

    ROLE_CHOICES = [
        (OWNER, "Owner"),
        (MANAGER, "Manager"),
        (MEMBER, "Member"),
        (VIEWER, "Viewer"),
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
        verbose_name = "Permissão do Biobank"
        verbose_name_plural = "Permissões do Biobank"

    def __str__(self):
        return f"{self.user.username} – {self.biobank.name} ({self.role})"
