from core.models.samples.origin import SampleOrigin


ORIGIN_VALUE_FIELDS = (
    "culture_status",
    "acquisition_source",
    "source_collection_name",
    "source_collection_accession",
    "collection_site_name",
    "collection_date",
    "geo_loc_name",
    "country_or_ocean",
    "latitude",
    "longitude",
    "coordinate_source",
    "coordinate_uncertainty_m",
    "depth_m",
    "elevation_m",
    "habitat",
    "environmental_medium",
    "env_broad_scale",
    "env_local_scale",
    "ecosystem",
    "ecosystem_category",
    "ecosystem_type",
    "ecosystem_subtype",
    "specific_ecosystem",
    "collection_method",
    "notes",
)


def origin_data_has_content(cleaned_data):
    """
    Return whether submitted provenance metadata contains an actual value.

    location_visibility alone does not create a SampleOrigin row.
    """
    for field_name in ORIGIN_VALUE_FIELDS:
        value = cleaned_data.get(
            field_name
        )

        if value is None:
            continue

        if isinstance(
            value,
            str,
        ):
            if value.strip():
                return True
            continue

        return True

    return False


def save_sample_origin(
    sample,
    cleaned_data,
):
    """
    Create, update or clear the Sample's geographic provenance.

    A completely blank provenance form removes an existing SampleOrigin
    row instead of preserving a meaningless empty object.
    """
    if not origin_data_has_content(
        cleaned_data
    ):
        SampleOrigin.objects.filter(
            sample=sample
        ).delete()

        return None

    origin, _created = (
        SampleOrigin.objects.get_or_create(
            sample=sample
        )
    )

    for field_name in (
        *ORIGIN_VALUE_FIELDS,
        "location_visibility",
    ):
        if field_name in cleaned_data:
            setattr(
                origin,
                field_name,
                cleaned_data[
                    field_name
                ],
            )

    origin.full_clean()
    origin.save()

    return origin
