"""
Canonical public catalog projection for B3 LIMS.

Every unauthenticated catalog surface, aggregate, visualization and
future public API must begin from these querysets rather than from the
internal inventory directly.

The public projection deliberately excludes lifecycle-hidden,
embargoed and private resources before any aggregation takes place.
"""

from django.db.models import (
    Count,
    Prefetch,
    Q,
)

from core.models import (
    Collection,
    Sample,
    SampleOrigin,
    Tag,
)


def public_samples_queryset():
    """
    Return Samples that may participate in the unauthenticated
    public catalog.

    This queryset intentionally mirrors
    is_sample_publicly_accessible() from core.permissions.samples.

    Public visibility requires all of the following:

    - active Sample;
    - explicit public flag;
    - no embargo;
    - no pending deletion / Trash state.

    Internal authorization, ownership, Research Group membership,
    Collection membership and access grants never expand this public
    projection.
    """
    return Sample.objects.filter(
        is_active=True,
        is_public=True,
        is_embargoed=False,
        deletion_requested_at__isnull=True,
    )


def public_collections_queryset():
    """
    Return Collections that may participate in the unauthenticated
    public catalog.

    Collection publication is explicit and lifecycle-aware.
    """
    return Collection.objects.filter(
        is_active=True,
        is_public=True,
    )


def public_collection_catalog_queryset():
    """
    Return public Collections prepared for safe rendering.

    Only active Tags are exposed to public templates. The filtered
    Tag objects are stored in ``public_tags`` so templates never need
    to traverse the unrestricted Collection.tags relation.
    """
    active_public_tags = (
        Tag.objects
        .filter(
            is_active=True,
        )
        .order_by(
            "name",
        )
    )

    return (
        public_collections_queryset()
        .prefetch_related(
            Prefetch(
                "tags",
                queryset=active_public_tags,
                to_attr="public_tags",
            )
        )
    )


def search_public_collections_queryset(
    query,
):
    """
    Search only metadata that is explicitly eligible for public
    disclosure.

    A public Collection may match through:

    - its own public name;
    - its own public description;
    - an active Collection Tag;
    - organism metadata from a public Sample;
    - sample type metadata from a public Sample.

    Private, embargoed, inactive and trashed Samples are excluded
    before Sample metadata participates in search.
    """
    normalized_query = str(
        query or ""
    ).strip()

    collections = (
        public_collection_catalog_queryset()
    )

    if not normalized_query:
        return collections

    public_sample_matches = (
        public_samples_queryset()
        .filter(
            Q(
                organism_name__icontains=(
                    normalized_query
                )
            )
            | Q(
                sample_type__icontains=(
                    normalized_query
                )
            )
        )
    )

    return (
        collections
        .filter(
            Q(
                name__icontains=(
                    normalized_query
                )
            )
            | Q(
                description__icontains=(
                    normalized_query
                )
            )
            | Q(
                tags__is_active=True,
                tags__name__icontains=(
                    normalized_query
                ),
            )
            | Q(
                samples__in=(
                    public_sample_matches
                )
            )
        )
        .distinct()
    )


def public_home_metrics():
    """
    Return top-level metrics for the unauthenticated Public Home.

    Every metric starts from a canonical public queryset.

    Geographic coverage is additionally restricted to SampleOrigin
    records whose location_visibility explicitly permits some level
    of public disclosure. Internal-only origins do not contribute
    even to the aggregate country/ocean count.
    """
    samples = public_samples_queryset()
    collections = public_collections_queryset()

    organisms = (
        samples
        .exclude(
            organism_name__isnull=True,
        )
        .exclude(
            organism_name="",
        )
        .values(
            "organism_name",
        )
        .distinct()
        .count()
    )

    geographic_origins = (
        samples
        .filter(
            origin__location_visibility__in=(
                SampleOrigin.LOCATION_APPROXIMATE,
                SampleOrigin.LOCATION_EXACT,
            ),
        )
        .exclude(
            origin__country_or_ocean="",
        )
        .values(
            "origin__country_or_ocean",
        )
        .distinct()
        .count()
    )

    return {
        "public_samples": (
            samples.count()
        ),
        "public_collections": (
            collections.count()
        ),
        "organisms": organisms,
        "geographic_origins": (
            geographic_origins
        ),
    }


def public_sample_type_distribution(
    limit=6,
):
    """
    Return the leading Sample types in the public catalog.

    Private, embargoed, inactive and trashed Samples have already
    been removed before aggregation.

    ``percentage`` uses all publicly accessible Samples as the
    denominator and is intended only for presentation of the
    server-rendered overview bars.
    """
    samples = public_samples_queryset()

    public_total = (
        samples.count()
    )

    rows = list(
        samples
        .exclude(
            sample_type__isnull=True,
        )
        .exclude(
            sample_type="",
        )
        .values(
            "sample_type",
        )
        .annotate(
            total=Count(
                "pk",
            )
        )
        .order_by(
            "-total",
            "sample_type",
        )[
            :limit
        ]
    )

    for row in rows:
        if public_total:
            row["percentage"] = round(
                (
                    row["total"]
                    / public_total
                )
                * 100,
                1,
            )
        else:
            row["percentage"] = 0

    return rows


def public_organism_distribution(
    limit=12,
):
    """
    Return the most represented organism names among publicly
    accessible Samples.

    Organism metadata participates only after the Sample has passed
    the canonical public projection. Private, embargoed, inactive and
    trashed Samples therefore cannot contribute to this aggregate.
    """
    return list(
        public_samples_queryset()
        .exclude(
            organism_name__isnull=True,
        )
        .exclude(
            organism_name="",
        )
        .values(
            "organism_name",
        )
        .annotate(
            total=Count(
                "pk",
            )
        )
        .order_by(
            "-total",
            "organism_name",
        )[
            :limit
        ]
    )



def public_geographic_distribution(
    limit=50,
):
    """
    Return publication-safe geographic coverage aggregated only at
    the country/ocean label level.

    Exact coordinates, collection-site names and other internal
    origin metadata are deliberately excluded from this projection.

    A Sample contributes only when:

    - the Sample passes public_samples_queryset();
    - its SampleOrigin explicitly permits approximate or exact
      public location disclosure;
    - country_or_ocean is populated.

    The browser therefore receives only ``location`` and ``total``.
    """
    rows = list(
        public_samples_queryset()
        .filter(
            origin__location_visibility__in=(
                SampleOrigin.LOCATION_APPROXIMATE,
                SampleOrigin.LOCATION_EXACT,
            ),
        )
        .exclude(
            origin__country_or_ocean__isnull=True,
        )
        .exclude(
            origin__country_or_ocean="",
        )
        .values(
            "origin__country_or_ocean",
        )
        .annotate(
            total=Count(
                "pk",
            )
        )
        .order_by(
            "-total",
            "origin__country_or_ocean",
        )[
            :limit
        ]
    )

    return [
        {
            "location": (
                row[
                    "origin__country_or_ocean"
                ]
            ),
            "total": row["total"],
        }
        for row in rows
    ]


def public_organism_sample_type_network(
    limit=60,
):
    """
    Return publication-safe Organism ↔ Sample type associations.

    Each row represents an aggregate edge derived only from Samples
    that have already passed the canonical public projection.

    The result intentionally contains no Sample IDs, owner metadata,
    Collection membership, storage information or internal origin
    information.
    """
    return list(
        public_samples_queryset()
        .exclude(
            organism_name__isnull=True,
        )
        .exclude(
            organism_name="",
        )
        .exclude(
            sample_type__isnull=True,
        )
        .exclude(
            sample_type="",
        )
        .values(
            "organism_name",
            "sample_type",
        )
        .annotate(
            total=Count(
                "pk",
            )
        )
        .order_by(
            "-total",
            "organism_name",
            "sample_type",
        )[
            :limit
        ]
    )

def featured_public_collections(
    limit=3,
):
    """
    Return recently updated public Collections with publication-safe
    metadata and publication-safe Sample counts.

    The count is calculated by intersecting Collection membership
    with public_samples_queryset(). It therefore never represents
    raw Collection membership.
    """
    collections = list(
        public_collection_catalog_queryset()
        .order_by(
            "-updated_at",
            "name",
        )[
            :limit
        ]
    )

    collection_ids = [
        collection.pk
        for collection in collections
    ]

    counts = {}

    if collection_ids:
        counts = {
            row["collections"]: row["total"]
            for row in (
                public_samples_queryset()
                .filter(
                    collections__pk__in=(
                        collection_ids
                    )
                )
                .values(
                    "collections",
                )
                .annotate(
                    total=Count(
                        "pk",
                        distinct=True,
                    )
                )
            )
        }

    for collection in collections:
        collection.public_sample_count = (
            counts.get(
                collection.pk,
                0,
            )
        )

    return collections


def public_home_context():
    """
    Build the publication-safe dynamic context for the Public Home.
    """
    return {
        "public_metrics": (
            public_home_metrics()
        ),
        "sample_type_distribution": (
            public_sample_type_distribution()
        ),
        "organism_distribution": (
            public_organism_distribution()
        ),
        "geographic_distribution": (
            public_geographic_distribution()
        ),
        "organism_sample_type_network": (
            public_organism_sample_type_network()
        ),
        "featured_collections": (
            featured_public_collections()
        ),
    }
