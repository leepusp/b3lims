"""
Canonical public catalog projection for B3 LIMS.

Every unauthenticated catalog surface, aggregate, visualization and
future public API must begin from these querysets rather than from the
internal inventory directly.

The public projection deliberately excludes lifecycle-hidden,
embargoed and private resources before any aggregation takes place.
"""

from django.db.models import (
    Prefetch,
    Q,
)

from core.models import (
    Collection,
    Sample,
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
