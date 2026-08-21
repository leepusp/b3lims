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

    CULTURE_CULTURED = "cultured"
    CULTURE_UNCULTURED = "uncultured"

    CULTURE_STATUS_CHOICES = [
        (
            CULTURE_CULTURED,
            "Cultured",
        ),
        (
            CULTURE_UNCULTURED,
            "Uncultured",
        ),
    ]

    ACQUISITION_ISOLATED_LAB = "isolated_lab"
    ACQUISITION_COLLABORATOR = "collaborator"
    ACQUISITION_CULTURE_COLLECTION = "culture_collection"
    ACQUISITION_EXTERNAL_REPOSITORY = "external_repository"
    ACQUISITION_OTHER = "other"

    ACQUISITION_SOURCE_CHOICES = [
        (
            ACQUISITION_ISOLATED_LAB,
            "Isolated by laboratory",
        ),
        (
            ACQUISITION_COLLABORATOR,
            "Obtained from collaborator",
        ),
        (
            ACQUISITION_CULTURE_COLLECTION,
            "Obtained from culture collection",
        ),
        (
            ACQUISITION_EXTERNAL_REPOSITORY,
            "Obtained from external repository",
        ),
        (
            ACQUISITION_OTHER,
            "Other",
        ),
    ]

    COORDINATE_MAP = "map"
    COORDINATE_GPS = "gps"
    COORDINATE_GAZETTEER = "gazetteer"
    COORDINATE_PROVIDER = "provider"
    COORDINATE_IMPORTED = "imported"
    COORDINATE_OTHER = "other"

    COORDINATE_SOURCE_CHOICES = [
        (
            COORDINATE_MAP,
            "Map selection",
        ),
        (
            COORDINATE_GPS,
            "GPS",
        ),
        (
            COORDINATE_GAZETTEER,
            "Gazetteer / geocoding service",
        ),
        (
            COORDINATE_PROVIDER,
            "Reported by provider",
        ),
        (
            COORDINATE_IMPORTED,
            "Imported metadata",
        ),
        (
            COORDINATE_OTHER,
            "Other",
        ),
    ]

    sample = models.OneToOneField(
        "core.Sample",
        on_delete=models.CASCADE,
        related_name="origin",
    )

    culture_status = models.CharField(
        max_length=20,
        choices=CULTURE_STATUS_CHOICES,
        blank=True,
        default="",
        verbose_name="Culture status",
        help_text=(
            "Whether the source organism or material was maintained "
            "as a culture at the time represented by this provenance."
        ),
    )

    acquisition_source = models.CharField(
        max_length=40,
        choices=ACQUISITION_SOURCE_CHOICES,
        blank=True,
        default="",
        verbose_name="Acquisition source",
        help_text=(
            "How the biological material represented by this Sample "
            "was originally acquired."
        ),
    )

    source_collection_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Source culture collection",
        help_text=(
            "Name of an external culture collection, repository or "
            "provider from which the material was obtained."
        ),
    )

    source_collection_accession = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Source collection accession",
        help_text=(
            "Accession, catalogue number or external identifier assigned "
            "by the source culture collection or repository."
        ),
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

    coordinate_source = models.CharField(
        max_length=30,
        choices=COORDINATE_SOURCE_CHOICES,
        blank=True,
        default="",
        verbose_name="Coordinate source",
        help_text=(
            "How the latitude / longitude pair was obtained."
        ),
    )

    coordinate_uncertainty_m = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(
                Decimal("0")
            ),
        ],
        verbose_name="Coordinate uncertainty (m)",
        help_text=(
            "Estimated horizontal uncertainty of the recorded "
            "coordinates in metres."
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

    ecosystem = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Highest-level ecosystem classification associated with "
            "the source environment."
        ),
    )

    ecosystem_category = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Ecosystem category",
        help_text=(
            "Second-level environmental classification."
        ),
    )

    ecosystem_type = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Ecosystem type",
        help_text=(
            "Environmental type within the selected ecosystem category."
        ),
    )

    ecosystem_subtype = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Ecosystem subtype",
        help_text=(
            "Environmental subtype within the selected ecosystem type."
        ),
    )

    specific_ecosystem = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Specific ecosystem",
        help_text=(
            "Most specific available environmental classification."
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


        has_coordinates = (
            has_latitude
            and has_longitude
        )

        coordinate_errors = {}

        if (
            self.coordinate_source
            and not has_coordinates
        ):
            coordinate_errors[
                "coordinate_source"
            ] = (
                "Coordinate source requires a complete latitude / "
                "longitude pair."
            )

        if (
            self.coordinate_uncertainty_m
            is not None
            and not has_coordinates
        ):
            coordinate_errors[
                "coordinate_uncertainty_m"
            ] = (
                "Coordinate uncertainty requires a complete latitude / "
                "longitude pair."
            )

        if coordinate_errors:
            raise ValidationError(
                coordinate_errors
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
