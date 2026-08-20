from __future__ import annotations

from .base import (
    StructureProviderError,
    StructureSearchQueryError,
)
from .models import (
    ProviderReport,
    StructureSearchResult,
)
from .providers import (
    beacons3d_exact,
    rcsb,
)


DEFAULT_PROVIDERS = (
    rcsb,
    beacons3d_exact,
)


def _provider_key(
    provider,
):
    return str(
        getattr(
            provider,
            "key",
            "",
        )
        or ""
    ).strip()


def _provider_name(
    provider,
):
    return str(
        getattr(
            provider,
            "display_name",
            "",
        )
        or _provider_key(
            provider
        )
    ).strip()


def _normalized_sequence_length(
    sequence,
):
    return len(
        "".join(
            str(
                sequence
                or ""
            ).split()
        )
    )


def search_structures_by_sequence(
    sequence,
    *,
    rows=10,
    providers=None,
):
    """
    Search multiple structure providers and return a normalized,
    deduplicated response.

    Provider order establishes precedence during
    deduplication.

    RCSB can therefore remain authoritative for experimental
    PDB polymer entities while later providers add distinct
    predicted/computational models.
    """
    selected_providers = tuple(
        providers
        if providers is not None
        else DEFAULT_PROVIDERS
    )

    if not selected_providers:
        raise StructureSearchQueryError(
            "At least one structure provider is required."
        )

    query_length = None

    deduplicated_hits = {}
    provider_reports = []

    for provider in selected_providers:
        provider_key = _provider_key(
            provider
        )

        provider_name = _provider_name(
            provider
        )

        if not provider_key:
            raise StructureSearchQueryError(
                "Structure provider key is required."
            )

        try:
            batch = (
                provider.search_by_sequence(
                    sequence,
                    rows=rows,
                )
            )

        except StructureSearchQueryError:
            #
            # Invalid input is not provider degradation.
            #
            raise

        except StructureProviderError as exc:
            provider_reports.append(
                ProviderReport(
                    provider=provider_key,
                    provider_name=provider_name,
                    state="degraded",
                    error=str(
                        exc
                    ),
                )
            )

            continue

        if query_length is None:
            query_length = (
                batch.query_length
            )

        elif (
            batch.query_length
            and batch.query_length
            != query_length
        ):
            raise StructureSearchQueryError(
                "Structure providers returned "
                "inconsistent query lengths."
            )

        for hit in batch.hits:
            #
            # First provider wins for the same canonical
            # structural object.
            #
            deduplicated_hits.setdefault(
                hit.canonical_key,
                hit,
            )

        provider_reports.append(
            ProviderReport(
                provider=batch.provider,
                provider_name=(
                    batch.provider_name
                ),
                state="available",
                total_count=(
                    batch.total_count
                ),
                returned_count=len(
                    batch.hits
                ),
            )
        )

    if query_length is None:
        #
        # All remote providers may legitimately be degraded.
        #
        query_length = (
            _normalized_sequence_length(
                sequence
            )
        )

    return StructureSearchResult(
        query_length=query_length,
        hits=tuple(
            deduplicated_hits.values()
        ),
        providers=tuple(
            provider_reports
        ),
    )
