from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


def normalize_metadata_text(value):
    """Normalize user-provided metadata text without changing letter case."""
    return " ".join((value or "").split())


class Keyword(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="core_keyword_name_ci_unique",
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = normalize_metadata_text(self.name)
        if not self.name:
            raise ValidationError({"name": "Keyword name is required."})
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class KeywordValue(models.Model):
    keyword = models.ForeignKey(
        Keyword,
        on_delete=models.PROTECT,
        related_name="values",
    )
    value = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("keyword__name", "value")
        constraints = [
            models.UniqueConstraint(
                "keyword",
                Lower("value"),
                name="core_keyword_value_ci_unique",
            ),
        ]

    def save(self, *args, **kwargs):
        self.value = normalize_metadata_text(self.value)
        if not self.value:
            raise ValidationError({"value": "Keyword value is required."})
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.keyword.name}: {self.value}"
