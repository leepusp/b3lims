from django.db import models
from django.contrib.auth.models import User

from core.models.tags.model import Tag
from core.models.keywords.model import KeywordValue
from core.models.research_groups.model import ResearchGroup


class Biobank(models.Model):
    """
    Top-level institutional entity.

    Represents a physical biobank, collection hub, or consortium-level
    structure responsible for biological material custody.
    """

    # =========================
    # BASIC METADATA
    # =========================
    name = models.CharField(max_length=200)

    description = models.TextField(
        blank=True,
        null=True,
        help_text="Institutional description of the biobank.",
    )

    # =========================
    # LOCATION
    # =========================
    location_label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable address or location label.",
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    # =========================
    # GOVERNANCE / ACCESS CONTROL
    # =========================
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="owned_biobanks",
        help_text="Primary biobank manager.",
    )

    research_group = models.ForeignKey(
        ResearchGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="biobanks",
        help_text="Research group responsible for this biobank.",
    )

    is_public = models.BooleanField(
        default=False,
        help_text="Marks this biobank as visible in public or institutional catalogs.",
    )

    # =========================
    # LIFECYCLE
    # =========================
    is_active = models.BooleanField(
        default=True,
        help_text="Indicates whether this biobank is operational.",
    )

    # =========================
    # CLASSIFICATION
    # =========================
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="biobanks",
    )

    keywords = models.ManyToManyField(
        KeywordValue,
        blank=True,
        related_name="biobanks",
    )

    def __str__(self):
        return self.name
