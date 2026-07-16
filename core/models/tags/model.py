from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


def normalize_metadata_name(value):
    """Normalize user-provided vocabulary labels without changing letter case."""
    return " ".join((value or "").split())


class Tag(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="core_tag_name_ci_unique",
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = normalize_metadata_name(self.name)
        if not self.name:
            raise ValidationError({"name": "Tag name is required."})
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
