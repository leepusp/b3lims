from django.conf import settings
from django.db import models

from .sample import Sample


EXTERNAL_SOURCE_NCBI = "ncbi"
EXTERNAL_SOURCE_BACDIVE = "bacdive"
EXTERNAL_SOURCE_ICTV = "ictv"
EXTERNAL_SOURCE_GTDB = "gtdb"

EXTERNAL_SOURCE_CHOICES = [
    (
        EXTERNAL_SOURCE_NCBI,
        "NCBI",
    ),
    (
        EXTERNAL_SOURCE_BACDIVE,
        "BacDive",
    ),
    (
        EXTERNAL_SOURCE_ICTV,
        "ICTV",
    ),
    (
        EXTERNAL_SOURCE_GTDB,
        "GTDB",
    ),
]


class SampleEnrichmentSnapshot(models.Model):
    """
    Append-only record of one external-data lookup.

    Snapshots preserve the exact external response separately from
    curated Sample metadata. No enrichment operation silently mutates
    the biological identity stored on Sample or its subtype.
    """

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="enrichment_snapshots",
    )

    source = models.CharField(
        max_length=32,
        choices=EXTERNAL_SOURCE_CHOICES,
    )

    query = models.TextField()

    request_url = models.TextField(
        blank=True,
    )

    source_version = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    source_record_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    http_status = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    success = models.BooleanField(
        default=False,
    )

    error_message = models.TextField(
        blank=True,
        default="",
    )

    raw_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    normalized_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    checksum_sha256 = models.CharField(
        max_length=64,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=(
            "sample_enrichment_snapshots_requested"
        ),
    )

    fetched_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-fetched_at",
            "-pk",
        ]

        indexes = [
            models.Index(
                fields=[
                    "sample",
                    "source",
                    "fetched_at",
                ],
                name="samp_enrich_src_time_idx",
            ),
        ]

        verbose_name = (
            "Sample Enrichment Snapshot"
        )

        verbose_name_plural = (
            "Sample Enrichment Snapshots"
        )

    def __str__(self):
        return (
            f"{self.sample.sample_id} "
            f"{self.get_source_display()} "
            f"{self.query}"
        )


class SampleExternalIdentifier(models.Model):
    """
    External accession or identifier linked to one Sample.

    Multiple identifiers of the same type are allowed when required,
    while is_primary identifies the currently preferred identifier.
    """

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="external_identifiers",
    )

    source = models.CharField(
        max_length=32,
        choices=EXTERNAL_SOURCE_CHOICES,
    )

    identifier_type = models.CharField(
        max_length=64,
    )

    identifier = models.CharField(
        max_length=255,
    )

    is_primary = models.BooleanField(
        default=False,
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "source",
            "identifier_type",
            "-is_primary",
            "identifier",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sample",
                    "source",
                    "identifier_type",
                    "identifier",
                ],
                name="uniq_sample_ext_identifier",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "sample",
                    "source",
                    "identifier_type",
                ],
                name="samp_ext_src_type_idx",
            ),
        ]

        verbose_name = (
            "Sample External Identifier"
        )

        verbose_name_plural = (
            "Sample External Identifiers"
        )

    def __str__(self):
        return (
            f"{self.sample.sample_id}: "
            f"{self.source}/"
            f"{self.identifier_type}="
            f"{self.identifier}"
        )


class SampleTaxonomyAssignment(models.Model):
    """
    Normalized source-specific taxonomy for one Sample.

    This is independent from curated Sample fields such as genus,
    species and strain. External assignments are reviewable evidence,
    not silent replacements for user-curated metadata.
    """

    STATUS_CANDIDATE = "candidate"
    STATUS_VERIFIED = "verified"
    STATUS_CONFLICT = "conflict"
    STATUS_UNRESOLVED = "unresolved"
    STATUS_STALE = "stale"

    MATCH_STATUS_CHOICES = [
        (
            STATUS_CANDIDATE,
            "Candidate",
        ),
        (
            STATUS_VERIFIED,
            "Verified",
        ),
        (
            STATUS_CONFLICT,
            "Conflict",
        ),
        (
            STATUS_UNRESOLVED,
            "Unresolved",
        ),
        (
            STATUS_STALE,
            "Stale",
        ),
    ]

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="taxonomy_assignments",
    )

    source = models.CharField(
        max_length=32,
        choices=EXTERNAL_SOURCE_CHOICES,
    )

    taxon_id = models.CharField(
        max_length=128,
    )

    scientific_name = models.CharField(
        max_length=255,
    )

    rank = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    domain_or_realm = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    kingdom = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    phylum = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    class_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    order_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    family = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    genus = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    species = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    lineage = models.JSONField(
        default=dict,
        blank=True,
    )

    match_status = models.CharField(
        max_length=16,
        choices=MATCH_STATUS_CHOICES,
        default=STATUS_CANDIDATE,
    )

    source_release = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    is_current = models.BooleanField(
        default=True,
    )

    snapshot = models.ForeignKey(
        SampleEnrichmentSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taxonomy_assignments",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=(
            "sample_taxonomy_assignments_reviewed"
        ),
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "source",
            "-is_current",
            "scientific_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sample",
                    "source",
                    "taxon_id",
                ],
                name="uniq_sample_tax_source_taxon",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "sample",
                    "source",
                    "is_current",
                ],
                name="samp_tax_src_curr_idx",
            ),
        ]

        verbose_name = (
            "Sample Taxonomy Assignment"
        )

        verbose_name_plural = (
            "Sample Taxonomy Assignments"
        )

    def __str__(self):
        return (
            f"{self.sample.sample_id}: "
            f"{self.get_source_display()} "
            f"{self.scientific_name} "
            f"({self.taxon_id})"
        )


class SampleTaxonomyReview(models.Model):
    """
    Append-only human review history for an external taxonomy assignment.

    SampleTaxonomyAssignment stores the latest review state, while this
    model preserves every human decision made over that assignment.
    """

    assignment = models.ForeignKey(
        SampleTaxonomyAssignment,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    previous_status = models.CharField(
        max_length=16,
        choices=(
            SampleTaxonomyAssignment
            .MATCH_STATUS_CHOICES
        ),
    )

    new_status = models.CharField(
        max_length=16,
        choices=(
            SampleTaxonomyAssignment
            .MATCH_STATUS_CHOICES
        ),
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=(
            "sample_taxonomy_reviews"
        ),
    )

    note = models.TextField(
        blank=True,
        default="",
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-reviewed_at",
            "-pk",
        ]

        indexes = [
            models.Index(
                fields=[
                    "assignment",
                    "reviewed_at",
                ],
                name="samp_tax_review_time_idx",
            ),
        ]

        verbose_name = (
            "Sample Taxonomy Review"
        )

        verbose_name_plural = (
            "Sample Taxonomy Reviews"
        )

    def __str__(self):
        return (
            f"{self.assignment}: "
            f"{self.previous_status} -> "
            f"{self.new_status}"
        )


class SampleGenomeAssemblyAssignment(models.Model):
    """
    Normalized NCBI Genome Assembly evidence for one Sample.

    Assembly metadata is kept independently from curated Sample identity.
    Resolution never silently rewrites organism, genus, species, strain,
    or other user-curated Sample fields.
    """

    STATUS_CANDIDATE = "candidate"
    STATUS_VERIFIED = "verified"
    STATUS_CONFLICT = "conflict"
    STATUS_UNRESOLVED = "unresolved"
    STATUS_STALE = "stale"

    MATCH_STATUS_CHOICES = [
        (
            STATUS_CANDIDATE,
            "Candidate",
        ),
        (
            STATUS_VERIFIED,
            "Verified",
        ),
        (
            STATUS_CONFLICT,
            "Conflict",
        ),
        (
            STATUS_UNRESOLVED,
            "Unresolved",
        ),
        (
            STATUS_STALE,
            "Stale",
        ),
    ]

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="genome_assembly_assignments",
    )

    source = models.CharField(
        max_length=32,
        choices=EXTERNAL_SOURCE_CHOICES,
    )

    accession = models.CharField(
        max_length=64,
    )

    current_accession = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    paired_accession = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    source_database = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    organism_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    taxon_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    assembly_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    assembly_level = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    assembly_status = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    assembly_type = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    refseq_category = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    release_date = models.CharField(
        max_length=32,
        blank=True,
        default="",
    )

    submitter = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    bioproject_accession = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    biosample_accession = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    total_sequence_length = (
        models.PositiveBigIntegerField(
            null=True,
            blank=True,
        )
    )

    number_of_contigs = (
        models.PositiveIntegerField(
            null=True,
            blank=True,
        )
    )

    number_of_scaffolds = (
        models.PositiveIntegerField(
            null=True,
            blank=True,
        )
    )

    contig_n50 = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    scaffold_n50 = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    gc_percent = models.FloatField(
        null=True,
        blank=True,
    )

    match_status = models.CharField(
        max_length=16,
        choices=MATCH_STATUS_CHOICES,
        default=STATUS_CANDIDATE,
    )

    is_current = models.BooleanField(
        default=True,
    )

    snapshot = models.ForeignKey(
        SampleEnrichmentSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="genome_assembly_assignments",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=(
            "sample_genome_assembly_assignments_reviewed"
        ),
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "source",
            "-is_current",
            "accession",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sample",
                    "source",
                    "accession",
                ],
                name="uniq_sample_asm_src_acc",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "sample",
                    "source",
                    "is_current",
                ],
                name="samp_asm_src_curr_idx",
            ),
        ]

        verbose_name = (
            "Sample Genome Assembly Assignment"
        )

        verbose_name_plural = (
            "Sample Genome Assembly Assignments"
        )

    def __str__(self):
        return (
            f"{self.sample.sample_id}: "
            f"{self.get_source_display()} "
            f"{self.accession}"
        )


class SampleGenomeAssemblyReview(models.Model):
    """
    Human review history for one external Genome Assembly assignment.

    History is append-only by service convention. The assignment stores
    the latest review state while this model preserves individual
    decisions.
    """

    assignment = models.ForeignKey(
        SampleGenomeAssemblyAssignment,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    previous_status = models.CharField(
        max_length=16,
        choices=(
            SampleGenomeAssemblyAssignment
            .MATCH_STATUS_CHOICES
        ),
    )

    new_status = models.CharField(
        max_length=16,
        choices=(
            SampleGenomeAssemblyAssignment
            .MATCH_STATUS_CHOICES
        ),
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=(
            "sample_genome_assembly_reviews"
        ),
    )

    note = models.TextField(
        blank=True,
        default="",
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-reviewed_at",
            "-pk",
        ]

        indexes = [
            models.Index(
                fields=[
                    "assignment",
                    "reviewed_at",
                ],
                name="samp_asm_review_time_idx",
            ),
        ]

        verbose_name = (
            "Sample Genome Assembly Review"
        )

        verbose_name_plural = (
            "Sample Genome Assembly Reviews"
        )

    def __str__(self):
        return (
            f"{self.assignment}: "
            f"{self.previous_status} -> "
            f"{self.new_status}"
        )
