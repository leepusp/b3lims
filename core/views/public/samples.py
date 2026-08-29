from django.core.paginator import Paginator
from django.shortcuts import (
    get_object_or_404,
    render,
)

from core.context import base_context
from core.services.public_catalog import (
    public_sample_catalog_queryset,
    public_sample_detail_record,
    public_sample_facets,
    search_public_samples_queryset,
)


def public_sample_list(
    request,
):
    """
    Display the publication-safe Sample catalog.

    Every result starts from the canonical public Sample projection.
    """
    query = (
        request.GET.get(
            "q",
            "",
        )
        or ""
    ).strip()

    sample_type = (
        request.GET.get(
            "sample_type",
            "",
        )
        or ""
    ).strip()

    genus = (
        request.GET.get(
            "genus",
            "",
        )
        or ""
    ).strip()

    species = (
        request.GET.get(
            "species",
            "",
        )
        or ""
    ).strip()

    samples = (
        search_public_samples_queryset(
            query,
            sample_type=sample_type,
            genus=genus,
            species=species,
        )
    )

    paginator = Paginator(
        samples,
        24,
    )

    page_obj = paginator.get_page(
        request.GET.get(
            "page"
        )
    )

    context = {
        "samples": page_obj.object_list,
        "page_obj": page_obj,
        "result_count": (
            paginator.count
        ),
        "query": query,
        "selected_sample_type": (
            sample_type
        ),
        "selected_genus": genus,
        "selected_species": species,
        "facets": (
            public_sample_facets()
        ),
    }

    context.update(
        base_context(
            request,
            public=True,
        )
    )

    return render(
        request,
        "public/samples/list.html",
        context,
    )


def public_sample_detail(
    request,
    sample_id,
):
    """
    Display one publication-approved Sample by its existing Sample ID.

    UUID, Micro QR, ownership, Research Group, storage and unrestricted
    origin metadata are not part of the public detail projection.
    """
    sample = get_object_or_404(
        public_sample_catalog_queryset(),
        sample_id=sample_id,
    )

    context = {
        "record": (
            public_sample_detail_record(
                sample
            )
        ),
    }

    context.update(
        base_context(
            request,
            public=True,
        )
    )

    return render(
        request,
        "public/samples/detail.html",
        context,
    )
