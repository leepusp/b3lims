from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models


class SampleOrigin(models.Model):
    """
    Geographic and environmental provenance of one Sample.

    This describes where the biological material originated or was
    collected. It is intentionally independent from Physical Storage,
    which describes where the Sample is currently stored in the LIMS.

    Coordinates use WGS84 decimal latitude/longitude and are valid for
    terrestrial, freshwater and marine/oceanic collection sites.
    """

    LOCATION_INTERNAL = "internal"
    LOCATION_APPROXIMATE = "approximate"
    LOCATION_EXACT = "exact"

    LOCATION_VISIBILITY_CHOICES = [
        (
            LOCATION_INTERNAL,
            "Internal only",
        ),
        (
            LOCATION_APPROXIMATE,
            "Public - approximate",
        ),
        (
            LOCATION_EXACT,
            "Public - exact",
        ),
    ]

    sample = models.OneToOneField(
        "core.Sample",
        on_delete=models.CASCADE,
        related_name="origin",
    )

    collection_site_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Human-readable name of the site where the material "
            "was collected."
        ),
    )

    collection_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Date on which the source material was collected."
        ),
    )

    geo_loc_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Geographic location",
        help_text=(
            "Geographic region, locality or water body associated "
            "with the collection site."
        ),
    )

    country_or_ocean = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Country / Ocean",
        help_text=(
            "Country, territory, sea or ocean containing the "
            "collection site."
        ),
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(
                Decimal("-90")
            ),
            MaxValueValidator(
                Decimal("90")
            ),
        ],
        help_text=(
            "WGS84 latitude in decimal degrees."
        ),
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(
                Decimal("-180")
            ),
            MaxValueValidator(
                Decimal("180")
            ),
        ],
        help_text=(
            "WGS84 longitude in decimal degrees."
        ),
    )

    depth_m = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(
                Decimal("0")
            ),
        ],
        verbose_name="Depth (m)",
        help_text=(
            "Depth below the local surface or water surface, "
            "in metres."
        ),
    )

    elevation_m = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Elevation / Altitude (m)",
        help_text=(
            "Elevation relative to mean sea level, in metres."
        ),
    )

    habitat = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Concise description of the habitat at the "
            "collection site."
        ),
    )

    environmental_medium = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Environmental medium",
        help_text=(
            "Material or medium from which the Sample originated, "
            "for example ocean water, soil, sediment or host tissue."
        ),
    )

    env_broad_scale = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Broad-scale environmental context",
        help_text=(
            "Broad environmental context compatible with MIxS-style "
            "provenance metadata."
        ),
    )

    env_local_scale = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Local environmental context",
        help_text=(
            "Local environmental feature compatible with MIxS-style "
            "provenance metadata."
        ),
    )

    collection_method = models.TextField(
        blank=True,
        help_text=(
            "Method or protocol used to collect the source material."
        ),
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Origin notes",
    )

    location_visibility = models.CharField(
        max_length=20,
        choices=LOCATION_VISIBILITY_CHOICES,
        default=LOCATION_INTERNAL,
        help_text=(
            "Controls whether geographic coordinates may later be "
            "exposed outside the authenticated internal interface."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "sample__sample_id",
        ]
        verbose_name = "Sample Origin"
        verbose_name_plural = "Sample Origins"

    def clean(self):
        super().clean()

        has_latitude = (
            self.latitude is not None
        )

        has_longitude = (
            self.longitude is not None
        )

        if has_latitude != has_longitude:
            raise ValidationError(
                {
                    "latitude": (
                        "Latitude and longitude must be provided together."
                    ),
                    "longitude": (
                        "Latitude and longitude must be provided together."
                    ),
                }
            )

    @property
    def has_coordinates(self):
        return bool(
            self.latitude is not None
            and self.longitude is not None
        )

    @property
    def coordinate_text(self):
        if not self.has_coordinates:
            return ""

        return (
            f"{self.latitude}, "
            f"{self.longitude}"
        )

    def __str__(self):
        location = (
            self.collection_site_name
            or self.geo_loc_name
            or self.country_or_ocean
            or self.coordinate_text
            or "Origin not described"
        )

        return (
            f"{self.sample.sample_id}: "
            f"{location}"
        )
