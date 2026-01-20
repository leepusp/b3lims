# core/models/keywords.py

from django.db import models


class Keyword(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name


class KeywordValue(models.Model):
    keyword = models.ForeignKey(Keyword, on_delete=models.CASCADE)
    value = models.CharField(max_length=255)

    # ❌ REMOVIDO: vínculos diretos exclusivos com entidades
    # sample = models.ForeignKey(...)
    # collection = models.ForeignKey(...)
    # biobank = models.ForeignKey(...)

    def __str__(self):
        return f"{self.keyword.name}: {self.value}"

