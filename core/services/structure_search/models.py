from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_SOURCE_TYPES = frozenset(
    {
        "experimental",
        "computational",
    }
)

VALID_MODEL_TYPES = frozenset(
    {
        "experimental",
        "template-based",
        "ab-initio",
        "conformational-ensemble",
        "other",
    }
)

VALID_PROVIDER_STATES = frozenset(
    {
        "available",
        "degraded",
    }
)


@dataclass(
    frozen=True,
    slots=True,
)
class StructureEntity:
    """
    One molecular entity exposed by a structure provider.

    This keeps model-level chain metadata without forcing
    provider-specific dictionaries into the normalized API.
    """

    entity_type: str = ""
    description: str = ""

    chain_ids: tuple[
        str,
        ...
    ] = ()

    identifier: str = ""
    identifier_category: str = ""
    entity_poly_type: str = ""

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "description": self.description,
            "chain_ids": list(
                self.chain_ids
            ),
            "identifier": self.identifier,
            "identifier_category": (
                self.identifier_category
            ),
            "entity_poly_type": (
                self.entity_poly_type
            ),
        }


@dataclass(
    frozen=True,
    slots=True,
)
class StructureHit:
    """
    Provider-neutral structure-search hit.

    canonical_key represents the strongest structural identity
    that the source can support without inventing identifiers.

    RCSB can identify a PDB polymer entity:

        pdb:6B3Q:2

    3D-Beacons does not expose that RCSB polymer entity ID in
    its sequence result. An experimental PDB result discovered
    there therefore uses the actual information available:

        pdb:6B3Q:uniprot:P01308:1-110

    A later cross-provider reconciliation layer may establish
    equivalence between those two keys.
    """

    provider: str
    provider_name: str

    source_type: str
    model_type: str

    accession: str
    canonical_key: str

    discovery_provider: str = ""

    entity_id: str = ""
    sequence_accession: str = ""

    title: str = ""
    description: str = ""

    #
    # Query-to-sequence-search-hit metrics.
    #
    identity: float | None = None
    sequence_coverage: float | None = None

    #
    # Provider model-to-reference-sequence metrics.
    #
    model_sequence_identity: float | None = None
    model_coverage: float | None = None

    coordinate_coverage: float | None = None
    score: float | None = None

    experimental_method: str = ""
    resolution: float | None = None

    coordinate_url: str = ""
    coordinate_format: str = ""
    model_page_url: str = ""

    sequence_start: int | None = None
    sequence_end: int | None = None

    #
    # Preserve the provider's native confidence scale.
    #
    # Examples:
    #
    #   pLDDT      -> [0, 100]
    #   QMEANDisCo -> [0, 1]
    #
    # These values must not be compared as if they shared one
    # numerical scale.
    #
    confidence_type: str = ""
    confidence_value: float | None = None
    confidence_version: str = ""

    chains: tuple[
        str,
        ...
    ] = ()

    entities: tuple[
        StructureEntity,
        ...
    ] = ()

    warnings: tuple[
        str,
        ...
    ] = ()

    def __post_init__(
        self,
    ):
        if not self.provider.strip():
            raise ValueError(
                "Structure provider is required."
            )

        if not self.provider_name.strip():
            raise ValueError(
                "Structure provider name is required."
            )

        if (
            self.source_type
            not in VALID_SOURCE_TYPES
        ):
            raise ValueError(
                "Invalid structure source_type: "
                f"{self.source_type!r}."
            )

        if (
            self.model_type
            not in VALID_MODEL_TYPES
        ):
            raise ValueError(
                "Invalid structure model_type: "
                f"{self.model_type!r}."
            )

        if not self.accession.strip():
            raise ValueError(
                "Structure accession is required."
            )

        if not self.canonical_key.strip():
            raise ValueError(
                "Structure canonical_key is required."
            )

        if (
            self.sequence_start is not None
            and self.sequence_start < 1
        ):
            raise ValueError(
                "sequence_start must be >= 1."
            )

        if (
            self.sequence_end is not None
            and self.sequence_end < 1
        ):
            raise ValueError(
                "sequence_end must be >= 1."
            )

        if (
            self.sequence_start is not None
            and self.sequence_end is not None
            and self.sequence_end
            < self.sequence_start
        ):
            raise ValueError(
                "sequence_end cannot precede "
                "sequence_start."
            )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_name": self.provider_name,
            "discovery_provider": (
                self.discovery_provider
            ),
            "source_type": self.source_type,
            "model_type": self.model_type,
            "accession": self.accession,
            "canonical_key": self.canonical_key,
            "entity_id": self.entity_id,
            "sequence_accession": (
                self.sequence_accession
            ),
            "title": self.title,
            "description": self.description,
            "identity": self.identity,
            "sequence_coverage": (
                self.sequence_coverage
            ),
            "model_sequence_identity": (
                self.model_sequence_identity
            ),
            "model_coverage": (
                self.model_coverage
            ),
            "coordinate_coverage": (
                self.coordinate_coverage
            ),
            "score": self.score,
            "experimental_method": (
                self.experimental_method
            ),
            "resolution": self.resolution,
            "coordinate_url": (
                self.coordinate_url
            ),
            "coordinate_format": (
                self.coordinate_format
            ),
            "model_page_url": (
                self.model_page_url
            ),
            "sequence_start": (
                self.sequence_start
            ),
            "sequence_end": (
                self.sequence_end
            ),
            "confidence_type": (
                self.confidence_type
            ),
            "confidence_value": (
                self.confidence_value
            ),
            "confidence_version": (
                self.confidence_version
            ),
            "chains": list(
                self.chains
            ),
            "entities": [
                entity.to_dict()
                for entity in self.entities
            ],
            "warnings": list(
                self.warnings
            ),
        }


@dataclass(
    frozen=True,
    slots=True,
)
class ProviderSearchBatch:
    """
    Normalized successful result from one provider.
    """

    provider: str
    provider_name: str

    query_length: int
    total_count: int

    hits: tuple[
        StructureHit,
        ...
    ]

    def __post_init__(
        self,
    ):
        if self.query_length < 0:
            raise ValueError(
                "query_length cannot be negative."
            )

        if self.total_count < 0:
            raise ValueError(
                "total_count cannot be negative."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class ProviderReport:
    """
    Provider health information returned by an orchestrated
    structure search.
    """

    provider: str
    provider_name: str
    state: str

    total_count: int = 0
    returned_count: int = 0

    error: str = ""

    def __post_init__(
        self,
    ):
        if (
            self.state
            not in VALID_PROVIDER_STATES
        ):
            raise ValueError(
                "Invalid provider state: "
                f"{self.state!r}."
            )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_name": self.provider_name,
            "state": self.state,
            "total_count": self.total_count,
            "returned_count": (
                self.returned_count
            ),
            "error": self.error,
        }


@dataclass(
    frozen=True,
    slots=True,
)
class StructureSearchResult:
    """
    Final provider-neutral and deduplicated structure result.
    """

    query_length: int

    hits: tuple[
        StructureHit,
        ...
    ]

    providers: tuple[
        ProviderReport,
        ...
    ]

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "query_length": (
                self.query_length
            ),
            "returned_count": len(
                self.hits
            ),
            "hits": [
                hit.to_dict()
                for hit in self.hits
            ],
            "providers": [
                provider.to_dict()
                for provider
                in self.providers
            ],
        }
