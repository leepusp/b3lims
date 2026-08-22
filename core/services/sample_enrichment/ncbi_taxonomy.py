import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from django.db import transaction

from core.models.samples.enrichment import (
    EXTERNAL_SOURCE_NCBI,
    SampleEnrichmentSnapshot,
    SampleExternalIdentifier,
    SampleTaxonomyAssignment,
)
from core.models.samples.subtypes import (
    Bacteria,
    format_bacterial_taxonomic_name,
)


NCBI_DATASETS_VERSION = "datasets-v2"

NCBI_TAXONOMY_BASE_URL = (
    "https://api.ncbi.nlm.nih.gov/"
    "datasets/v2/taxonomy/taxon"
)

NCBI_USER_AGENT = (
    "DaVinci-Biobank/"
    "sample-external-enrichment-v1"
)


class NCBITaxonomyLookupError(RuntimeError):
    pass


def _canonical_json_bytes(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode("utf-8")


def _payload_checksum(payload):
    return hashlib.sha256(
        _canonical_json_bytes(
            payload
        )
    ).hexdigest()


def build_ncbi_taxonomy_url(query):
    normalized = (
        str(query or "")
        .strip()
    )

    if not normalized:
        raise ValueError(
            "NCBI taxonomy query cannot be blank."
        )

    encoded = urllib.parse.quote(
        normalized,
        safe="",
    )

    return (
        f"{NCBI_TAXONOMY_BASE_URL}/"
        f"{encoded}/dataset_report"
    )


def _network_url(base_url):
    api_key = (
        os.environ
        .get(
            "NCBI_API_KEY",
            "",
        )
        .strip()
    )

    if not api_key:
        return base_url

    separator = (
        "&"
        if "?" in base_url
        else "?"
    )

    return (
        base_url
        + separator
        + "api_key="
        + urllib.parse.quote(
            api_key,
            safe="",
        )
    )


def _fetch_ncbi_taxonomy_payload(
    public_url,
):
    request = urllib.request.Request(
        _network_url(
            public_url
        ),
        headers={
            "Accept": (
                "application/json"
            ),
            "User-Agent": (
                NCBI_USER_AGENT
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            status = int(
                getattr(
                    response,
                    "status",
                    200,
                )
                or 200
            )

            payload = json.load(
                response
            )

    except urllib.error.HTTPError as exc:
        raise NCBITaxonomyLookupError(
            "NCBI returned HTTP "
            f"{exc.code}."
        ) from exc

    except urllib.error.URLError as exc:
        raise NCBITaxonomyLookupError(
            "Could not reach NCBI: "
            f"{exc.reason}"
        ) from exc

    except TimeoutError as exc:
        raise NCBITaxonomyLookupError(
            "NCBI request timed out."
        ) from exc

    except json.JSONDecodeError as exc:
        raise NCBITaxonomyLookupError(
            "NCBI returned invalid JSON."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise NCBITaxonomyLookupError(
            "NCBI returned an unexpected "
            "response type."
        )

    return (
        payload,
        status,
    )


def _classification_name(
    classification,
    key,
):
    value = (
        classification.get(key)
        or {}
    )

    if not isinstance(
        value,
        dict,
    ):
        return ""

    return (
        str(
            value.get(
                "name",
                "",
            )
            or ""
        )
        .strip()
    )


def normalize_ncbi_taxonomy_payload(
    payload,
):
    reports = (
        payload.get(
            "reports"
        )
        or []
    )

    if not isinstance(
        reports,
        list,
    ):
        reports = []

    total_count = payload.get(
        "total_count"
    )

    if len(reports) == 0:
        return {
            "resolution_status": (
                "not_found"
            ),
            "result_count": 0,
            "total_count": (
                total_count
            ),
        }

    if len(reports) != 1:
        return {
            "resolution_status": (
                "ambiguous"
            ),
            "result_count": (
                len(reports)
            ),
            "total_count": (
                total_count
            ),
        }

    report = reports[0]

    if not isinstance(
        report,
        dict,
    ):
        return {
            "resolution_status": (
                "unresolved"
            ),
            "result_count": 1,
            "total_count": (
                total_count
            ),
        }

    taxonomy = (
        report.get(
            "taxonomy"
        )
        or {}
    )

    if not isinstance(
        taxonomy,
        dict,
    ):
        taxonomy = {}

    current_name = (
        taxonomy.get(
            "current_scientific_name"
        )
        or {}
    )

    if not isinstance(
        current_name,
        dict,
    ):
        current_name = {}

    classification = (
        taxonomy.get(
            "classification"
        )
        or {}
    )

    if not isinstance(
        classification,
        dict,
    ):
        classification = {}

    raw_tax_id = taxonomy.get(
        "tax_id"
    )

    taxon_id = (
        str(raw_tax_id)
        if raw_tax_id is not None
        else ""
    )

    scientific_name = (
        str(
            current_name.get(
                "name",
                "",
            )
            or ""
        )
        .strip()
    )

    rank = (
        str(
            taxonomy.get(
                "rank",
                "",
            )
            or ""
        )
        .strip()
        .lower()
    )

    domain_or_realm = (
        _classification_name(
            classification,
            "domain",
        )
        or
        _classification_name(
            classification,
            "realm",
        )
    )

    normalized = {
        "resolution_status": (
            "resolved"
            if (
                taxon_id
                and scientific_name
            )
            else "unresolved"
        ),
        "result_count": 1,
        "total_count": (
            total_count
        ),
        "taxon_id": taxon_id,
        "scientific_name": (
            scientific_name
        ),
        "rank": rank,
        "authority": (
            str(
                current_name.get(
                    "authority",
                    "",
                )
                or ""
            )
            .strip()
        ),
        "domain_or_realm": (
            domain_or_realm
        ),
        "kingdom": (
            _classification_name(
                classification,
                "kingdom",
            )
        ),
        "phylum": (
            _classification_name(
                classification,
                "phylum",
            )
        ),
        "class_name": (
            _classification_name(
                classification,
                "class",
            )
        ),
        "order_name": (
            _classification_name(
                classification,
                "order",
            )
        ),
        "family": (
            _classification_name(
                classification,
                "family",
            )
        ),
        "genus": (
            _classification_name(
                classification,
                "genus",
            )
        ),
        "species": (
            _classification_name(
                classification,
                "species",
            )
        ),
        "classification": (
            classification
        ),
        "parents": (
            taxonomy.get(
                "parents"
            )
            or []
        ),
        "secondary_tax_ids": (
            taxonomy.get(
                "secondary_tax_ids"
            )
            or []
        ),
    }

    return normalized


def _as_bacterium(sample):
    if isinstance(
        sample,
        Bacteria,
    ):
        return sample

    return (
        Bacteria.objects
        .filter(
            pk=sample.pk
        )
        .first()
    )


def suggest_ncbi_taxonomy_query(
    sample,
):
    bacterium = _as_bacterium(
        sample
    )

    if bacterium is None:
        return ""

    return (
        format_bacterial_taxonomic_name(
            bacterium.genus,
            bacterium.species,
            "",
        )
        .strip()
    )


def _match_status_for_sample(
    sample,
    normalized,
):
    if (
        normalized.get(
            "resolution_status"
        )
        != "resolved"
    ):
        return (
            SampleTaxonomyAssignment
            .STATUS_UNRESOLVED
        )

    curated_name = (
        suggest_ncbi_taxonomy_query(
            sample
        )
    )

    external_name = (
        normalized.get(
            "scientific_name",
            "",
        )
        .strip()
    )

    if (
        curated_name
        and external_name
        and curated_name.casefold()
        != external_name.casefold()
    ):
        return (
            SampleTaxonomyAssignment
            .STATUS_CONFLICT
        )

    return (
        SampleTaxonomyAssignment
        .STATUS_CANDIDATE
    )


def _failure_snapshot(
    sample,
    user,
    query,
    public_url,
    message,
):
    raw_payload = {}

    return (
        SampleEnrichmentSnapshot
        .objects
        .create(
            sample=sample,
            source=(
                EXTERNAL_SOURCE_NCBI
            ),
            query=query,
            request_url=public_url,
            source_version=(
                NCBI_DATASETS_VERSION
            ),
            success=False,
            error_message=message,
            raw_payload=raw_payload,
            normalized_payload={},
            checksum_sha256=(
                _payload_checksum(
                    raw_payload
                )
            ),
            requested_by=user,
        )
    )


def resolve_and_store_ncbi_taxonomy(
    sample,
    user,
    query,
):
    normalized_query = (
        str(query or "")
        .strip()
    )

    if not normalized_query:
        raise ValueError(
            "NCBI taxonomy query "
            "cannot be blank."
        )

    public_url = (
        build_ncbi_taxonomy_url(
            normalized_query
        )
    )

    try:
        (
            payload,
            http_status,
        ) = (
            _fetch_ncbi_taxonomy_payload(
                public_url
            )
        )

    except NCBITaxonomyLookupError as exc:
        _failure_snapshot(
            sample,
            user,
            normalized_query,
            public_url,
            str(exc),
        )

        raise

    normalized = (
        normalize_ncbi_taxonomy_payload(
            payload
        )
    )

    taxon_id = (
        normalized.get(
            "taxon_id",
            "",
        )
        .strip()
    )

    match_status = (
        _match_status_for_sample(
            sample,
            normalized,
        )
    )

    with transaction.atomic():
        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .create(
                sample=sample,
                source=(
                    EXTERNAL_SOURCE_NCBI
                ),
                query=normalized_query,
                request_url=public_url,
                source_version=(
                    NCBI_DATASETS_VERSION
                ),
                source_record_id=(
                    taxon_id
                ),
                http_status=(
                    http_status
                ),
                success=True,
                raw_payload=payload,
                normalized_payload=(
                    normalized
                ),
                checksum_sha256=(
                    _payload_checksum(
                        payload
                    )
                ),
                requested_by=user,
            )
        )

        assignment = None
        external_identifier = None

        if (
            normalized.get(
                "resolution_status"
            )
            == "resolved"
            and taxon_id
        ):
            (
                SampleExternalIdentifier
                .objects
                .filter(
                    sample=sample,
                    source=(
                        EXTERNAL_SOURCE_NCBI
                    ),
                    identifier_type=(
                        "tax_id"
                    ),
                    is_primary=True,
                )
                .exclude(
                    identifier=taxon_id
                )
                .update(
                    is_primary=False
                )
            )

            (
                external_identifier,
                _,
            ) = (
                SampleExternalIdentifier
                .objects
                .update_or_create(
                    sample=sample,
                    source=(
                        EXTERNAL_SOURCE_NCBI
                    ),
                    identifier_type=(
                        "tax_id"
                    ),
                    identifier=taxon_id,
                    defaults={
                        "is_primary": True,
                    },
                )
            )

            (
                SampleTaxonomyAssignment
                .objects
                .filter(
                    sample=sample,
                    source=(
                        EXTERNAL_SOURCE_NCBI
                    ),
                    is_current=True,
                )
                .exclude(
                    taxon_id=taxon_id
                )
                .update(
                    is_current=False
                )
            )

            previous = (
                SampleTaxonomyAssignment
                .objects
                .filter(
                    sample=sample,
                    source=(
                        EXTERNAL_SOURCE_NCBI
                    ),
                    taxon_id=taxon_id,
                )
                .first()
            )

            if (
                previous is not None
                and previous.match_status
                ==
                SampleTaxonomyAssignment
                .STATUS_VERIFIED
            ):
                match_status = (
                    SampleTaxonomyAssignment
                    .STATUS_VERIFIED
                )

            (
                assignment,
                _,
            ) = (
                SampleTaxonomyAssignment
                .objects
                .update_or_create(
                    sample=sample,
                    source=(
                        EXTERNAL_SOURCE_NCBI
                    ),
                    taxon_id=taxon_id,
                    defaults={
                        "scientific_name": (
                            normalized[
                                "scientific_name"
                            ]
                        ),
                        "rank": (
                            normalized[
                                "rank"
                            ]
                        ),
                        "domain_or_realm": (
                            normalized[
                                "domain_or_realm"
                            ]
                        ),
                        "kingdom": (
                            normalized[
                                "kingdom"
                            ]
                        ),
                        "phylum": (
                            normalized[
                                "phylum"
                            ]
                        ),
                        "class_name": (
                            normalized[
                                "class_name"
                            ]
                        ),
                        "order_name": (
                            normalized[
                                "order_name"
                            ]
                        ),
                        "family": (
                            normalized[
                                "family"
                            ]
                        ),
                        "genus": (
                            normalized[
                                "genus"
                            ]
                        ),
                        "species": (
                            normalized[
                                "species"
                            ]
                        ),
                        "lineage": {
                            "classification": (
                                normalized[
                                    "classification"
                                ]
                            ),
                            "parents": (
                                normalized[
                                    "parents"
                                ]
                            ),
                            "secondary_tax_ids": (
                                normalized[
                                    "secondary_tax_ids"
                                ]
                            ),
                        },
                        "match_status": (
                            match_status
                        ),
                        "source_release": "",
                        "is_current": True,
                        "snapshot": snapshot,
                    },
                )
            )

    return {
        "snapshot": snapshot,
        "assignment": assignment,
        "external_identifier": (
            external_identifier
        ),
        "normalized": normalized,
    }
