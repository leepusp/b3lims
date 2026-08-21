import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator

# Imports retained for model integrity
from core.models.collections.collection import Collection
from core.models.biobanks.biobank import Biobank
from core.models.tags.model import Tag
from core.models.keywords.model import KeywordValue

# Research group model
from core.models.research_groups.model import ResearchGroup

class Sample(models.Model):
    BIOSAFETY_LEVEL_CHOICES = [
        ("NB-1", "NB-1"),
        ("NB-2", "NB-2"),
        ("NB-3", "NB-3"),
        ("NB-4", "NB-4"),
    ]
    """
    CEPID B3 biological sample.
    Base model used by specialized sample types.
    """
    STATUS_CHOICES = [
        ("pending", "Pending Receipt"),
        ("qc", "Quality Control"),
        ("available", "Available / Approved"),
        ("rejected", "Rejected / Nonviable"),
        ("depleted", "Depleted"),
    ]

    # Identification
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    sample_id = models.CharField(max_length=100, unique=True)
    sample_type = models.CharField(max_length=100, blank=True, null=True)
    biosafety_level = models.CharField(
        max_length=10,
        choices=BIOSAFETY_LEVEL_CHOICES,
        blank=True,
        null=True,
        verbose_name="Biosafety level",
        help_text="Biosafety level required for handling this sample.",
    )
    organism_name = models.CharField(max_length=255, blank=True, null=True)

    # ==========================================
    # ORGANIZATION
    # ==========================================
    biobank = models.ForeignKey(Biobank, on_delete=models.SET_NULL, null=True, blank=True, related_name="samples")
    # A sample may belong to multiple collections.
    collections = models.ManyToManyField(Collection, blank=True, related_name="samples")

    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_samples")

    # Research group / laboratory association
    research_group = models.ForeignKey(
        ResearchGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="samples",
        help_text="Research group or laboratory associated with this sample."
    )

    # Status, governance and lifecycle
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    is_public = models.BooleanField(
        default=False,
        help_text=(
            "Allows public metadata access when the Sample is active "
            "and not embargoed."
        ),
    )
    is_embargoed = models.BooleanField(
        default=False,
        help_text=(
            "Restricts public access while preserving authorized "
            "internal access."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Controls whether the Sample is part of the active inventory."
        ),
    )
    aliquot_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text=(
            "Number of physical aliquots represented by this Sample record."
        ),
    )

    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )
    deactivated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="deactivated_samples",
    )

    deletion_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )
    deletion_requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="sample_deletion_requests",
    )
    purge_after = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        help_text=(
            "Earliest time at which a Sample in Trash may be "
            "permanently deleted."
        ),
    )

    # ELN and technical metadata
    scientific_notes = models.TextField(blank=True, null=True)

    # Physical storage metadata
    storage_location = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # General classification
    tags = models.ManyToManyField(Tag, blank=True, related_name="samples")
    keywords = models.ManyToManyField(KeywordValue, blank=True, related_name="samples")

    # Lineage / biological network
    lineage = models.ManyToManyField(
        'self',
        through='core.SampleRelationship',
        through_fields=('source_sample', 'target_sample'),
        symmetrical=False,
        blank=True,
        related_name='derived_from_lineage'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):

        # Biobank and Collection assignments are intentionally
        # independent.

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sample_id} - {self.organism_name or 'No organism'}"


class SampleDeletionAudit(models.Model):
    """
    Durable audit record created immediately before permanent Sample deletion.

    This record deliberately has no ForeignKey to Sample so the audit survives
    deletion of the original inventory record and its CASCADE dependents.
    """

    original_sample_pk = models.PositiveBigIntegerField(
        db_index=True,
    )
    original_sample_uuid = models.UUIDField(
        db_index=True,
    )
    original_sample_id = models.CharField(
        max_length=100,
        db_index=True,
    )
    original_sample_type = models.CharField(
        max_length=100,
        blank=True,
    )
    original_organism_name = models.CharField(
        max_length=255,
        blank=True,
    )

    deleted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sample_deletion_audits",
    )

    snapshot = models.JSONField(
        default=dict,
    )
    storage_cleanup_errors = models.JSONField(
        default=list,
        blank=True,
    )

    class Meta:
        ordering = ["-deleted_at", "-pk"]
        verbose_name = "Sample Deletion Audit"
        verbose_name_plural = "Sample Deletion Audits"

    def __str__(self):
        return (
            f"{self.original_sample_id} "
            f"(deleted {self.deleted_at:%Y-%m-%d %H:%M})"
        )


# ========================================================================
# PHYSICAL STORAGE COMPATIBILITY
# ========================================================================
class SampleStorageLevel(models.Model):
    """
    Compatibility representation of a hierarchical physical storage path.
    Example: "Freezer 1 > Shelf 2 > Box A":
    - level_index 0: "Freezer 1" (root level)
    - level_index 1: "Shelf 2" (level 1)
    - level_index 2: "Box A" (level 2)
    """
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='storage_levels')
    name = models.CharField(max_length=150, help_text="Storage level name (for example, Freezer 1)")
    level_index = models.PositiveIntegerField(help_text="Zero represents the root storage level")

    class Meta:
        ordering = ['level_index']
        # A sample can have only one entry for each level index.
        unique_together = ('sample', 'level_index')
        verbose_name = "Storage Level"
        verbose_name_plural = "Storage Levels"

    def __str__(self):
        return f"[{self.level_index}] {self.name} (Sample: {self.sample.sample_id})"
