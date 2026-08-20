from __future__ import annotations

from core.services import rcsb_pdb

from ..base import (
    StructureProviderError,
    StructureSearchQueryError,
)
from ..models import (
    ProviderSearchBatch,
    StructureHit,
)
from ..normalize import (
    optional_float,
    optional_fraction,
    pdb_canonical_key,
    string_tuple,
)


key = "rcsb"
display_name = "RCSB PDB"


def _normalize_hit(
    raw_hit,
):
    pdb_id = str(
        raw_hit.get(
            "pdb_id"
        )
        or ""
    ).strip().upper()

    entity_id = str(
        raw_hit.get(
            "entity_id"
        )
        or ""
    ).strip()

    return StructureHit(
        provider=key,
        provider_name=display_name,
        source_type="experimental",
        model_type="experimental",
        accession=pdb_id,
        canonical_key=pdb_canonical_key(
            pdb_id,
            entity_id,
        ),
        entity_id=entity_id,
        title=str(
            raw_hit.get(
                "title"
            )
            or ""
        ).strip(),
        description=str(
            raw_hit.get(
                "description"
            )
            or ""
        ).strip(),
        identity=optional_fraction(
            raw_hit.get(
                "identity"
            )
        ),
        sequence_coverage=(
            optional_fraction(
                raw_hit.get(
                    "query_coverage"
                )
            )
        ),
        coordinate_coverage=None,
        score=optional_float(
            raw_hit.get(
                "score"
            )
        ),
        experimental_method=str(
            raw_hit.get(
                "experimental_method"
            )
            or ""
        ).strip(),
        resolution=optional_float(
            raw_hit.get(
                "resolution"
            )
        ),
        chains=string_tuple(
            raw_hit.get(
                "chains"
            )
            or ()
        ),
        warnings=string_tuple(
            raw_hit.get(
                "warnings"
            )
            or ()
        ),
    )


def search_by_sequence(
    sequence,
    *,
    rows=10,
):
    """
    Adapt the existing production RCSB sequence-search service
    to the provider-neutral Structure Search contract.

    The existing PDB API remains unchanged.
    """
    try:
        payload = (
            rcsb_pdb.search_pdb_by_sequence(
                sequence,
                rows=rows,
            )
        )

    except rcsb_pdb.RcsbPdbQueryError as exc:
        raise StructureSearchQueryError(
            str(
                exc
            )
        ) from exc

    except rcsb_pdb.RcsbPdbSearchError as exc:
        raise StructureProviderError(
            str(
                exc
            )
        ) from exc

    normalized_hits = []

    for raw_hit in (
        payload.get(
            "hits"
        )
        or []
    ):
        if not isinstance(
            raw_hit,
            dict,
        ):
            continue

        try:
            normalized_hits.append(
                _normalize_hit(
                    raw_hit
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            #
            # One malformed upstream hit must not invalidate
            # otherwise valid provider results.
            #
            continue

    return ProviderSearchBatch(
        provider=key,
        provider_name=display_name,
        query_length=int(
            payload.get(
                "query_length"
            )
            or 0
        ),
        total_count=max(
            0,
            int(
                payload.get(
                    "total_count"
                )
                or 0
            ),
        ),
        hits=tuple(
            normalized_hits
        ),
    )
