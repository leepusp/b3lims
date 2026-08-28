from django.shortcuts import render

from core.context import base_context
from core.services.public_catalog import (
    public_home_context,
)


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
