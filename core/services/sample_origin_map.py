from django.urls import reverse


def build_sample_origin_distribution_context(
    samples_qs,
):
    """
    Build the internal geographic distribution dataset for an
    already-authorized Sample queryset.

    This service deliberately does not decide Sample visibility.
    Callers must supply a queryset that has already passed the
    appropriate authorization boundary.
    """
    qs = (
        samples_qs
        .select_related(
            "biobank",
            "owner",
            "research_group",
            "origin",
        )
    )

    total = qs.count()

    origin_qs = (
        qs
        .filter(
            origin__isnull=False,
        )
        .select_related(
            "origin",
        )
    )

    coordinate_qs = (
        origin_qs
        .exclude(
            origin__latitude__isnull=True,
        )
        .exclude(
            origin__longitude__isnull=True,
        )
    )

    points = []

    for sample in coordinate_qs:
        origin = sample.origin

        points.append(
            {
                "id": sample.pk,
                "sample_id": (
                    sample.sample_id
                    or ""
                ),
                "sample_type": (
                    sample.sample_type
                    or ""
                ),
                "organism_name": (
                    sample.organism_name
                    or ""
                ),
                "status": (
                    sample.status
                    or ""
                ),
                "status_label": (
                    sample.get_status_display()
                ),
                "owner": (
                    sample.owner.username
                    if sample.owner_id
                    else ""
                ),
                "research_group": (
                    sample.research_group.name
                    if sample.research_group_id
                    else ""
                ),
                "biobank": (
                    sample.biobank.name
                    if sample.biobank_id
                    else ""
                ),
                "is_public": bool(
                    sample.is_public
                ),
                "is_embargoed": bool(
                    sample.is_embargoed
                ),
                "collection_site_name": (
                    origin.collection_site_name
                    or ""
                ),
                "collection_date": (
                    origin.collection_date.isoformat()
                    if origin.collection_date
                    else ""
                ),
                "geo_loc_name": (
                    origin.geo_loc_name
                    or ""
                ),
                "country_or_ocean": (
                    origin.country_or_ocean
                    or ""
                ),
                "latitude": float(
                    origin.latitude
                ),
                "longitude": float(
                    origin.longitude
                ),
                "depth_m": (
                    float(
                        origin.depth_m
                    )
                    if origin.depth_m is not None
                    else None
                ),
                "elevation_m": (
                    float(
                        origin.elevation_m
                    )
                    if origin.elevation_m is not None
                    else None
                ),
                "habitat": (
                    origin.habitat
                    or ""
                ),
                "environmental_medium": (
                    origin.environmental_medium
                    or ""
                ),
                "env_broad_scale": (
                    origin.env_broad_scale
                    or ""
                ),
                "env_local_scale": (
                    origin.env_local_scale
                    or ""
                ),
                "location_visibility": (
                    origin.location_visibility
                ),
                "detail_url": reverse(
                    "sample_detail",
                    args=[
                        sample.pk,
                    ],
                ),
            }
        )

    def unique_values(
        key,
    ):
        return sorted(
            {
                str(
                    point.get(
                        key,
                        "",
                    )
                    or ""
                )
                for point in points
                if point.get(
                    key
                )
            },
            key=str.casefold,
        )

    coordinate_count = len(
        points
    )

    return {
        "sample_origin_points": points,
        "sample_origin_map_stats": {
            "total": total,
            "with_origin": (
                origin_qs.count()
            ),
            "with_coordinates": (
                coordinate_count
            ),
            "without_coordinates": (
                total
                - coordinate_count
            ),
        },
        "sample_origin_filter_types": (
            unique_values(
                "sample_type"
            )
        ),
        "sample_origin_filter_statuses": (
            sorted(
                {
                    (
                        point["status"],
                        point["status_label"],
                    )
                    for point in points
                    if point["status"]
                },
                key=lambda item: (
                    item[1].casefold()
                ),
            )
        ),
        "sample_origin_filter_biobanks": (
            unique_values(
                "biobank"
            )
        ),
        "sample_origin_filter_groups": (
            unique_values(
                "research_group"
            )
        ),
        "sample_origin_filter_locations": (
            unique_values(
                "country_or_ocean"
            )
        ),
        "sample_origin_filter_environments": (
            unique_values(
                "environmental_medium"
            )
        ),
        "sample_origin_filter_habitats": (
            unique_values(
                "habitat"
            )
        ),
        "sample_origin_filter_broad_scales": (
            unique_values(
                "env_broad_scale"
            )
        ),
        "sample_origin_filter_local_scales": (
            unique_values(
                "env_local_scale"
            )
        ),
        "sample_origin_filter_sites": (
            unique_values(
                "collection_site_name"
            )
        ),
    }
