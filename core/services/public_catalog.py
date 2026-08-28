"""
Canonical public catalog projection for B3 LIMS.

Every unauthenticated catalog surface, aggregate, visualization and
future public API must begin from these querysets rather than from the
internal inventory directly.

The public projection deliberately excludes lifecycle-hidden,
embargoed and private resources before any aggregation takes place.
"""

from core.models import (
    Collection,
    Sample,
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
