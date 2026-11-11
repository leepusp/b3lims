from django.db import models

from .sample import Sample


class SampleOrganism(models.Model):
    """One organism of a sample. A mixed culture or a phage with its host has several rows.

    The taxon comes from one of the local taxonomy databases (``source`` and ``taxon_id``, with a frozen
    ``lineage``) or is typed by hand when none has a match (``source`` = manual, no taxon id).
    """

    ROLE_PRIMARY = "primary"
    ROLE_MEMBER = "member"
    ROLE_HOST = "host"
    ROLE_ASSOCIATED = "associated"
    ROLE_CHOICES = [
        (ROLE_PRIMARY, "Main organism"),
        (ROLE_MEMBER, "Member of the mixture"),
        (ROLE_HOST, "Host"),
        (ROLE_ASSOCIATED, "Associated"),
    ]

    SOURCE_NCBI = "ncbi"
    SOURCE_GTDB = "gtdb"
    SOURCE_ICTV = "ictv"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_NCBI, "NCBI taxonomy (local copy)"),
        (SOURCE_GTDB, "GTDB (local copy)"),
        (SOURCE_ICTV, "ICTV (local copy)"),
        (SOURCE_MANUAL, "Typed by hand"),
    ]

    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="organisms")
    position = models.PositiveSmallIntegerField(default=0, db_default=0)
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default=ROLE_MEMBER, db_default="member")
    name = models.CharField(max_length=255)
    strain = models.CharField(max_length=100, blank=True, default="", db_default="")
    source = models.CharField(max_length=8, choices=SOURCE_CHOICES, default=SOURCE_MANUAL, db_default="manual")
    taxon_id = models.CharField(max_length=128, blank=True, default="", db_default="")
    rank = models.CharField(max_length=64, blank=True, default="", db_default="")
    # [{"taxid", "rank", "name"}] from the root down to the taxon, as in the index at the time.
    lineage = models.JSONField(default=list, blank=True)
    taxonomy_version = models.CharField(max_length=64, blank=True, default="", db_default="")
    notes = models.CharField(max_length=255, blank=True, default="", db_default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["sample", "position"], name="uniq_sample_organism_position"),
        ]

    def __str__(self):
        return f"{self.sample_id}: {self.name} ({self.get_role_display()})"

    @property
    def display_name(self):
        return f"{self.name} {self.strain}".strip()
