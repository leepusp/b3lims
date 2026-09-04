from django.shortcuts import render
from django.views.decorators.http import require_safe

from core.context import base_context
from core.services.public_catalog import (
    public_biobank_records,
    public_home_context,
)


@require_safe
def public_home(
    request,
):
    """
    Render the dynamic public landing page.

    All catalog statistics and featured resources originate from
    the canonical public catalog projection.
    """
    context = (
        public_home_context()
    )

    context[
        "featured_biobanks"
    ] = public_biobank_records(
        limit=3,
    )

    context.update(
        base_context(
            request,
            public=True,
        )
    )

    return render(
        request,
        "public/index.html",
        context,
    )
