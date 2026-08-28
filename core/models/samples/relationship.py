from django.contrib.auth.models import User
from django.db import models

from core.models.samples.sample import Sample


class SampleRelationship(models.Model):
    """
    Graph model for tracking lineage, derivation, and biological
    relationships between Samples.

    A Sample may have multiple source and derived Samples.
    """

    RELATIONSHIP_TYPES = [
        # Lineage and physical inventory
        (
            "aliquot",
            "Aliquot (exact copy in another tube)",
        ),
        (
            "passage",
            "Passage / Subculture",
        ),
        (
            "mutated_from",
            "Mutation / Modification of",
        ),

        # Biological interactions and engineering
        (
            "assembled_from",
            "Assembled from (Vector + Insert)",
        ),
        (
            "extracted_from",
            "Extracted from (DNA/RNA)",
        ),
        (
            "infects",
            "Infects (Host Range)",
        ),
        (
            "other",
            "Other Relationship",
        ),
    ]

    source_sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="outgoing_relationships",
        help_text="Source sample",
    )

    target_sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="incoming_relationships",
        help_text="Target or derived sample",
    )

    relationship_type = models.CharField(
        max_length=50,
        choices=RELATIONSHIP_TYPES,
        default="aliquot",
    )

    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Protocol or derivation method details.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        # Prevent duplicate relationships with the same direction and type.
        unique_together = (
            "source_sample",
            "target_sample",
            "relationship_type",
        )
        verbose_name = "Sample Relationship"
        verbose_name_plural = "Sample Relationships"

    def __str__(self):
        return (
            f"{self.source_sample.sample_id} "
            f"[{self.get_relationship_type_display()}] "
            f"-> {self.target_sample.sample_id}"
        )
