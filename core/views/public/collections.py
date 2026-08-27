from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    render,
)

from core.context import base_context
from core.models import Collection


def public_collection_list(
    request,
):
    """
    Display the active public Collection catalog.
    """
    query = (
        request.GET.get(
            "q",
            "",
        )
        or ""
    ).strip()

    collections = (
        Collection.objects
        .filter(
            is_public=True,
            is_active=True,
        )
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
    Display one active public Collection.
    """
    collection = get_object_or_404(
        Collection,
        id=collection_id,
        is_public=True,
        is_active=True,
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
