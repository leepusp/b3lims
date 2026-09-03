from django.shortcuts import (
    get_object_or_404,
    render,
)

from core.context import base_context
from core.services.public_catalog import (
    public_biobank_record,
    public_biobank_records,
    public_biobanks_queryset,
)


def public_biobank_list(
    request,
):
    """
    Render the publication-safe institutional Biobank directory.

    No internal Biobank model object is placed directly in the
    template context.
    """
    biobanks = (
        public_biobank_records()
    )

    mapped_biobanks = [
        biobank
        for biobank in biobanks
        if biobank["mapped"]
    ]

    context = base_context(
        request,
        public=True,
    )

    context.update(
        {
            "biobanks": biobanks,
            "mapped_biobanks": (
                mapped_biobanks
            ),
        }
    )

    return render(
        request,
        "public/biobanks/list.html",
        context,
    )


def public_biobank_detail(
    request,
    biobank_id,
):
    """
    Render one publication-safe Biobank profile.

    Private and inactive Biobanks deliberately resolve as 404.
    """
    biobank = get_object_or_404(
        public_biobanks_queryset(),
        pk=biobank_id,
    )

    record = (
        public_biobank_record(
            biobank
        )
    )

    context = base_context(
        request,
        public=True,
    )

    context.update(
        {
            "biobank": record,
        }
    )

    return render(
        request,
        "public/biobanks/detail.html",
        context,
    )
