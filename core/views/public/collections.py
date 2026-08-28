from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    render,
)

from core.context import base_context
from core.services.public_catalog import (
    public_collections_queryset,
)


def public_collection_list(
    request,
):
    """
    Display the active public Collection catalog.

    The query begins exclusively from the canonical public catalog
    projection so subsequent search/filter operations cannot expand
    visibility into private or inactive Collections.
    """
    query = (
        request.GET.get(
            "q",
            "",
        )
        or ""
    ).strip()

    collections = (
        public_collections_queryset()
        .prefetch_related(
            "tags",
        )
        .order_by(
            "name",
        )
    )

    if query:
        collections = (
            collections
            .filter(
                Q(
                    name__icontains=query
                )
                | Q(
                    description__icontains=query
                )
                | Q(
                    tags__name__icontains=query
                )
            )
            .distinct()
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
    """
    collection = get_object_or_404(
        public_collections_queryset(),
        id=collection_id,
    )

    context = {
        "collection": collection,
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
