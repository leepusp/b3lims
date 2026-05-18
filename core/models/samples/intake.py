from django.contrib.auth.models import User
from django.db import models

from core.models.biobanks.biobank import Biobank
from core.models.collections.collection import Collection
from core.models.samples.sample import Sample


class SampleImportBatch(models.Model):
    """A table upload session used to stage multiple sample records before registration."""

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("validated", "Validated"),
        ("partially_used", "Partially used"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="sample_import_batches",
    )
    original_file = models.FileField(upload_to="sample_imports/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="uploaded")
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sample import batch"
        verbose_name_plural = "Sample import batches"

    def __str__(self):
        return f"Import batch #{self.pk} - {self.original_filename or 'uploaded file'}"


class SampleIntakeRecord(models.Model):
    """One imported spreadsheet row that can be used to pre-fill the sample form."""

    STATUS_CHOICES = [
        ("waiting_review", "Waiting review"),
        ("ready_to_fill", "Ready to fill form"),
        ("used_for_sample", "Used for sample"),
        ("rejected", "Rejected"),
    ]

    batch = models.ForeignKey(
        SampleImportBatch,
        on_delete=models.CASCADE,
        related_name="records",
    )
    row_number = models.PositiveIntegerField()

    sample = models.ForeignKey(
        Sample,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intake_records",
    )

    imported_sample_id = models.CharField(max_length=100, blank=True, null=True)
    sample_type = models.CharField(max_length=100, blank=True, null=True)
    organism_name = models.CharField(max_length=255, blank=True, null=True)

    biobank_name = models.CharField(max_length=200, blank=True, null=True)
    collection_name = models.CharField(max_length=200, blank=True, null=True)

    matched_biobank = models.ForeignKey(
        Biobank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sample_intake_records",
    )
    matched_collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sample_intake_records",
    )

    storage_location = models.CharField(max_length=255, blank=True, null=True)
    provider = models.CharField(max_length=255, blank=True, null=True)
    research_group_name = models.CharField(max_length=255, blank=True, null=True)
    is_public = models.BooleanField(default=False)
    scientific_notes = models.TextField(blank=True, null=True)

    # Future movement/receipt metadata.
    intake_type = models.CharField(max_length=100, blank=True, null=True)
    source_biobank_name = models.CharField(max_length=200, blank=True, null=True)
    destination_biobank_name = models.CharField(max_length=200, blank=True, null=True)
    expected_arrival_date = models.CharField(max_length=50, blank=True, null=True)
    temperature_condition = models.CharField(max_length=100, blank=True, null=True)
    movement_notes = models.TextField(blank=True, null=True)

    raw_data = models.JSONField(default=dict, blank=True)
    normalized_data = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="waiting_review")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["batch", "row_number"]
        unique_together = ("batch", "row_number")
        verbose_name = "Sample intake record"
        verbose_name_plural = "Sample intake records"

    @property
    def can_fill_form(self):
        return not self.validation_errors

    def __str__(self):
        return f"Row {self.row_number}: {self.imported_sample_id or 'no sample_id'}"
