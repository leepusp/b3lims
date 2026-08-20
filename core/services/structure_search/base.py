from __future__ import annotations

from typing import Protocol

from .models import ProviderSearchBatch


class StructureSearchQueryError(
    ValueError
):
    """
    Invalid local structure-search query.
    """


class StructureProviderError(
    RuntimeError
):
    """
    One remote structure provider could not complete a query.

    The orchestrator may continue with other providers.
    """


class StructureSearchProvider(
    Protocol
):
    key: str
    display_name: str

    def search_by_sequence(
        self,
        sequence: str,
        *,
        rows: int = 10,
    ) -> ProviderSearchBatch:
        ...
