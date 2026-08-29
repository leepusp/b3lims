from django.shortcuts import (
    get_object_or_404,
    render,
)

from core.context import base_context
from core.services.public_catalog import (
    public_collection_catalog_queryset,
    public_sample_catalog_queryset,
    search_public_collections_queryset,
)


def public_collection_list(
    request,
):
    """
    Display the active public Collection catalog.

    Search begins exclusively from the canonical public projection.
    Related Sample metadata can participate only after the Sample
    itself satisfies the public publication boundary.
    """
    query = (
        request.GET.get(
            "q",
            "",
        )
        or ""
    ).strip()

    collections = (
        search_public_collections_queryset(
            query
        )
        .order_by(
            "name",
        )
    )

    context = {
        "collections": collections,
        "query": query,
    }

    context.update(
        base_context(
            request,
            public=True,
        )
    )

    return render(
        request,
        "public/collections/list.html",
        context,
    )


def public_collection_detail(
    request,
    collection_id,
):
    """
    Display one Collection from the canonical public projection.

    The template receives only the publication-safe Collection
    projection, including active public_tags.
    """
    collection = get_object_or_404(
        public_collection_catalog_queryset(),
        id=collection_id,
    )

    public_samples = list(
        public_sample_catalog_queryset()
        .filter(
            collections=collection,
        )
        .order_by(
            "sample_id",
        )
    )

    context = {
        "collection": collection,
        "public_samples": public_samples,
    }

    context.update(
        base_context(
            request,
            public=True,
        )
    )

    return render(
        request,
        "public/collections/detail.html",
        context,
    )
