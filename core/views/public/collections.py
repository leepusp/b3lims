from django.shortcuts import render, get_object_or_404
from django.db.models import Q

from core.models import Collection
from core.context import base_context


def public_collection_list(request):
    """
    Catálogo público de coleções do Biobank.
    """

    query = request.GET.get("q", "").strip()

    collections = (
        Collection.objects
        .filter(is_public=True)  # <--- CORREÇÃO 1: "visibility" trocado por "is_public"
        # .select_related("biobank")  # <--- CORREÇÃO 2: Removido pois não existe campo "biobank" na Collection
        .prefetch_related("tags")
        .order_by("name")
    )

    if query:
        collections = collections.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()

    context = {
        "collections": collections,
        "query": query,
    }

    context.update(base_context(request, public=True))

    return render(
        request,
        "public/collections/list.html",
        context,
   )


def public_collection_detail(request, collection_id):
    """
    Página pública de detalhe de uma coleção.
    """

    collection = get_object_or_404(
        Collection,
        id=collection_id,
        is_public=True,  # <--- CORREÇÃO 3: "visibility" trocado por "is_public"
    )

    context = {
        "collection": collection,
    }

    context.update(base_context(request, public=True))

    return render(
        request,
        "public/collections/detail.html",
        context,
    )
