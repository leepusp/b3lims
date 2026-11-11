from django.conf import settings
from django.db import models

from .sample import Sample


class SampleReferenceData(models.Model):
    """One piece of reference metadata a user chose to attach to a sample from a local database.

    The value is frozen when attached, together with its source and version, so the record stays
    reproducible even when the database is updated later.
    """

    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="reference_data")
    source = models.CharField(max_length=20, db_default="")
    source_version = models.CharField(max_length=50, blank=True, db_default="")
    group = models.CharField(max_length=40, blank=True, db_default="")
    key = models.CharField(max_length=60, db_default="")
    label = models.CharField(max_length=120, db_default="")
    value = models.TextField(blank=True, db_default="")
    organism_name = models.CharField(max_length=255, blank=True, db_default="")
    taxon_ref = models.CharField(max_length=128, blank=True, db_default="")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group", "label", "id"]
        constraints = [models.UniqueConstraint(fields=["sample", "source", "key"], name="uniq_sample_reference_item")]

    def __str__(self):
        return f"{self.label}: {self.value[:40]}"
