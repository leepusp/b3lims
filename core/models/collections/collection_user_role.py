from django.db import models
from django.contrib.auth.models import User


class CollectionUserRole(models.Model):
    """
    Define permissões locais de usuário dentro de uma Collection.
    Atua como uma ACL leve.
    """

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

    ROLE_CHOICES = [
        (OWNER, "Orientador"),
        (EDITOR, "Editor"),
        (VIEWER, "Visualizador"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="collection_roles",
    )

    collection = models.ForeignKey(
        "core.Collection",
        on_delete=models.CASCADE,
        related_name="user_roles",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=VIEWER,
    )

    class Meta:
        unique_together = ("user", "collection")
        verbose_name = "Permissão da Collection"
        verbose_name_plural = "Permissões da Collection"
        ordering = ["role", "user__username"]

    def __str__(self):
        return f"{self.user.username} – {self.collection.name} ({self.role})"

