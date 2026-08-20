from __future__ import annotations

from ..models import (
    ProviderSearchBatch,
)
from . import beacons3d


key = "beacons3d-exact"
display_name = "3D-Beacons exact models"


def search_by_sequence(
    sequence,
    *,
    rows=10,
):
    """
    Provider-protocol adapter for exact-sequence computational
    models discovered through 3D-Beacons.

    The underlying model provider remains stored on each
    StructureHit, for example:

        alphafold-db
        swiss-model

    while this batch identifies the discovery service.
    """
    batch = (
        beacons3d.search_exact_models_by_sequence(
            sequence,
            rows=rows,
        )
    )

    return ProviderSearchBatch(
        provider=key,
        provider_name=display_name,
        query_length=batch.query_length,
        total_count=batch.total_count,
        hits=batch.hits,
    )
