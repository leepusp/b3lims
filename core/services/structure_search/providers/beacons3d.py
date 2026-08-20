from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from ..base import (
    StructureProviderError,
    StructureSearchQueryError,
)
from ..models import (
    ProviderSearchBatch,
    StructureEntity,
    StructureHit,
)
from ..normalize import (
    optional_float,
    optional_fraction,
    string_tuple,
)


key = "beacons3d"
display_name = "3D-Beacons"

BASE_API = (
    "https://www.ebi.ac.uk/"
    "pdbe/pdbe-kb/3dbeacons/api/v2"
)

SEARCH_ENDPOINT = (
    f"{BASE_API}/sequence/search"
)

RESULT_ENDPOINT = (
    f"{BASE_API}/sequence/result"
)

SUMMARY_ENDPOINT = (
    f"{BASE_API}/sequence/summary"
)

REQUEST_TIMEOUT = 15

POLL_ATTEMPTS = 3
POLL_INTERVAL_SECONDS = 1.0

MAX_RESPONSE_BYTES = (
    25
    * 1024
    * 1024
)

MAX_SEQUENCE_LENGTH = 10000

USER_AGENT = (
    "Biobank-MolecularRegistry/2026 "
    "3D-Beacons-Structure-Search"
)

_ALLOWED_SEQUENCE = re.compile(
    r"^[A-Z]+$"
)

_PDB_IDENTIFIER = re.compile(
    r"^[0-9][A-Z0-9]{3}$",
    flags=re.IGNORECASE,
)


def _normalize_sequence(
    sequence,
):
    normalized = "".join(
        str(
            sequence
            or ""
        ).split()
    ).upper()

    if not normalized:
        raise StructureSearchQueryError(
            "Protein sequence is required."
        )

    if len(
        normalized
    ) > MAX_SEQUENCE_LENGTH:
        raise StructureSearchQueryError(
            "Protein sequence exceeds the "
            f"{MAX_SEQUENCE_LENGTH}-residue "
            "3D-Beacons query limit."
        )

    if not _ALLOWED_SEQUENCE.fullmatch(
        normalized
    ):
        raise StructureSearchQueryError(
            "Protein sequence must contain "
            "letters only."
        )

    return normalized


def _normalize_rows(
    rows,
):
    try:
        rows = int(
            rows
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise StructureSearchQueryError(
            "rows must be an integer."
        ) from exc

    if rows < 1:
        raise StructureSearchQueryError(
            "rows must be at least 1."
        )

    return min(
        rows,
        100,
    )


def _read_response_body(
    response,
):
    raw = response.read(
        MAX_RESPONSE_BYTES
        + 1
    )

    if len(
        raw
    ) > MAX_RESPONSE_BYTES:
        raise StructureProviderError(
            "3D-Beacons response exceeded "
            "the local safety limit."
        )

    return raw


def _decode_json(
    raw,
):
    try:
        return json.loads(
            raw.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise StructureProviderError(
            "3D-Beacons returned an invalid "
            "JSON response."
        ) from exc


def _request_json(
    url,
    *,
    method="GET",
    payload=None,
    timeout=REQUEST_TIMEOUT,
):
    allowed_exact = {
        SEARCH_ENDPOINT,
        RESULT_ENDPOINT,
        SUMMARY_ENDPOINT,
    }

    allowed_query_prefixes = (
        RESULT_ENDPOINT
        + "?",
        SUMMARY_ENDPOINT
        + "?",
    )

    if (
        url not in allowed_exact
        and not url.startswith(
            allowed_query_prefixes
        )
    ):
        raise StructureProviderError(
            "Unsupported 3D-Beacons endpoint."
        )

    data = None

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    if payload is not None:
        data = json.dumps(
            payload,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )

        headers[
            "Content-Type"
        ] = "application/json"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            status = int(
                response.status
            )

            raw = _read_response_body(
                response
            )

    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(
                4096
            )
        except Exception:
            raw = b""

        detail = raw.decode(
            "utf-8",
            errors="replace",
        ).strip()

        message = (
            f"3D-Beacons returned HTTP "
            f"{exc.code}."
        )

        if detail:
            message += (
                " "
                + detail[
                    :1000
                ]
            )

        raise StructureProviderError(
            message
        ) from exc

    except (
        urllib.error.URLError,
        TimeoutError,
        socket.timeout,
        OSError,
    ) as exc:
        raise StructureProviderError(
            "Could not contact the "
            "3D-Beacons service: "
            f"{exc}"
        ) from exc

    return (
        status,
        _decode_json(
            raw
        ),
    )


def submit_sequence_search(
    sequence,
):
    """
    Submit one sequence-search job and return its 3D-Beacons
    job identifier.

    This function does not poll.
    """
    sequence = _normalize_sequence(
        sequence
    )

    status, payload = _request_json(
        SEARCH_ENDPOINT,
        method="POST",
        payload={
            "sequence": sequence,
        },
    )

    if status not in {
        200,
        202,
    }:
        raise StructureProviderError(
            "Unexpected 3D-Beacons sequence "
            f"submission status {status}."
        )

    if not isinstance(
        payload,
        dict,
    ):
        raise StructureProviderError(
            "3D-Beacons sequence submission "
            "did not return an object."
        )

    job_id = str(
        payload.get(
            "job_id"
        )
        or ""
    ).strip()

    if not job_id:
        raise StructureProviderError(
            "3D-Beacons sequence submission "
            "did not return a job_id."
        )

    return job_id


def get_sequence_search_result(
    job_id,
):
    """
    Return:

        ("complete", list_payload)

    or:

        ("pending", None)

    The remote API defines HTTP 200 as complete and HTTP 202
    as still processing.
    """
    job_id = str(
        job_id
        or ""
    ).strip()

    if not job_id:
        raise StructureSearchQueryError(
            "3D-Beacons job_id is required."
        )

    quoted_job_id = (
        urllib.parse.quote(
            job_id,
            safe="",
        )
    )

    status, payload = _request_json(
        (
            RESULT_ENDPOINT
            + "?job_id="
            + quoted_job_id
        )
    )

    if status == 202:
        return (
            "pending",
            None,
        )

    if status != 200:
        raise StructureProviderError(
            "Unexpected 3D-Beacons sequence "
            f"result status {status}."
        )

    if not isinstance(
        payload,
        list,
    ):
        raise StructureProviderError(
            "Completed 3D-Beacons sequence "
            "result is not a list."
        )

    return (
        "complete",
        payload,
    )


def _provider_slug(
    value,
):
    text = str(
        value
        or ""
    ).strip().lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    ).strip(
        "-"
    )

    return (
        text
        or "unknown"
    )


def _optional_int(
    value,
):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _model_category(
    value,
):
    normalized = str(
        value
        or ""
    ).strip().upper()

    mapping = {
        "EXPERIMENTALLY DETERMINED": (
            "experimental",
            "experimental",
        ),
        "TEMPLATE-BASED": (
            "computational",
            "template-based",
        ),
        "AB-INITIO": (
            "computational",
            "ab-initio",
        ),
        "CONFORMATIONAL ENSEMBLE": (
            "computational",
            "conformational-ensemble",
        ),
    }

    return mapping.get(
        normalized,
        (
            "computational",
            "other",
        ),
    )


def _structure_entities(
    raw_entities,
):
    normalized = []

    for raw in (
        raw_entities
        or []
    ):
        if not isinstance(
            raw,
            dict,
        ):
            continue

        normalized.append(
            StructureEntity(
                entity_type=str(
                    raw.get(
                        "entity_type"
                    )
                    or ""
                ).strip(),
                description=str(
                    raw.get(
                        "description"
                    )
                    or ""
                ).strip(),
                chain_ids=string_tuple(
                    raw.get(
                        "chain_ids"
                    )
                    or ()
                ),
                identifier=str(
                    raw.get(
                        "identifier"
                    )
                    or ""
                ).strip(),
                identifier_category=str(
                    raw.get(
                        "identifier_category"
                    )
                    or ""
                ).strip(),
                entity_poly_type=str(
                    raw.get(
                        "entity_poly_type"
                    )
                    or ""
                ).strip(),
            )
        )

    return tuple(
        normalized
    )


def _matched_chains(
    entities,
    sequence_accession,
):
    sequence_accession = str(
        sequence_accession
        or ""
    ).strip().upper()

    matched = []

    fallback = []

    for entity in entities:
        if (
            entity.entity_type.upper()
            != "POLYMER"
        ):
            continue

        for chain in entity.chain_ids:
            if chain not in fallback:
                fallback.append(
                    chain
                )

        identifier = (
            entity.identifier.upper()
        )

        identifier_category = (
            entity.identifier_category.upper()
        )

        if (
            sequence_accession
            and identifier
            == sequence_accession
            and identifier_category
            == "UNIPROT"
        ):
            for chain in entity.chain_ids:
                if chain not in matched:
                    matched.append(
                        chain
                    )

    return tuple(
        matched
        or fallback
    )


def _iter_model_summaries(
    value,
):
    if isinstance(
        value,
        dict,
    ):
        if (
            "model_identifier"
            in value
            and "provider"
            in value
        ):
            yield value

        for child in value.values():
            yield from _iter_model_summaries(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            yield from _iter_model_summaries(
                child
            )


def _best_hsp(
    raw_hit,
):
    candidates = [
        hsp
        for hsp in (
            raw_hit.get(
                "hit_hsps"
            )
            or []
        )
        if isinstance(
            hsp,
            dict,
        )
    ]

    if not candidates:
        return {}

    def score(
        hsp,
    ):
        value = optional_float(
            hsp.get(
                "hsp_bit_score"
            )
        )

        return (
            value
            if value is not None
            else float(
                "-inf"
            )
        )

    return max(
        candidates,
        key=score,
    )


def _query_coverage(
    hsp,
    query_length,
):
    align_length = _optional_int(
        hsp.get(
            "hsp_align_len"
        )
    )

    if (
        align_length is None
        or query_length < 1
    ):
        return None

    return min(
        1.0,
        max(
            0.0,
            align_length
            / query_length,
        ),
    )


def _canonical_key(
    *,
    raw_model,
    provider_slug,
    sequence_accession,
    sequence_start,
    sequence_end,
):
    model_identifier = str(
        raw_model.get(
            "model_identifier"
        )
        or ""
    ).strip()

    if not model_identifier:
        raise ValueError(
            "3D-Beacons model_identifier "
            "is required."
        )

    source_type, _ = _model_category(
        raw_model.get(
            "model_category"
        )
    )

    upper_identifier = (
        model_identifier.upper()
    )

    if (
        source_type
        == "experimental"
        and _PDB_IDENTIFIER.fullmatch(
            upper_identifier
        )
    ):
        accession = (
            str(
                sequence_accession
                or ""
            ).strip().upper()
            or "UNKNOWN"
        )

        if (
            sequence_start is not None
            and sequence_end is not None
        ):
            range_key = (
                f"{sequence_start}-"
                f"{sequence_end}"
            )
        else:
            range_key = "UNSPECIFIED"

        return (
            f"pdb:{upper_identifier}:"
            f"uniprot:{accession}:"
            f"{range_key}"
        )

    if (
        provider_slug
        == "alphafold-db"
        or upper_identifier.startswith(
            "AF-"
        )
    ):
        return (
            "alphafold:"
            + upper_identifier
        )

    return (
        "model:"
        + provider_slug
        + ":"
        + model_identifier
    )


def _normalize_model(
    raw_model,
    *,
    raw_hit,
    query_length,
):
    model_identifier = str(
        raw_model.get(
            "model_identifier"
        )
        or ""
    ).strip()

    provider_name = str(
        raw_model.get(
            "provider"
        )
        or ""
    ).strip()

    if (
        not model_identifier
        or not provider_name
    ):
        raise ValueError(
            "Incomplete 3D-Beacons model."
        )

    provider_slug = _provider_slug(
        provider_name
    )

    sequence_accession = str(
        raw_hit.get(
            "accession"
        )
        or ""
    ).strip()

    sequence_start = _optional_int(
        raw_model.get(
            "uniprot_start"
        )
    )

    sequence_end = _optional_int(
        raw_model.get(
            "uniprot_end"
        )
    )

    source_type, model_type = (
        _model_category(
            raw_model.get(
                "model_category"
            )
        )
    )

    entities = _structure_entities(
        raw_model.get(
            "entities"
        )
    )

    hsp = _best_hsp(
        raw_hit
    )

    query_identity = optional_fraction(
        hsp.get(
            "hsp_identity"
        )
    )

    query_coverage = _query_coverage(
        hsp,
        query_length,
    )

    return StructureHit(
        provider=provider_slug,
        provider_name=provider_name,
        discovery_provider=key,
        source_type=source_type,
        model_type=model_type,
        accession=model_identifier,
        canonical_key=_canonical_key(
            raw_model=raw_model,
            provider_slug=provider_slug,
            sequence_accession=(
                sequence_accession
            ),
            sequence_start=sequence_start,
            sequence_end=sequence_end,
        ),
        sequence_accession=(
            sequence_accession
        ),
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
        identity=query_identity,
        sequence_coverage=(
            query_coverage
        ),
        model_sequence_identity=(
            optional_fraction(
                raw_model.get(
                    "sequence_identity"
                )
            )
        ),
        model_coverage=(
            optional_fraction(
                raw_model.get(
                    "coverage"
                )
            )
        ),
        coordinate_coverage=None,
        score=optional_float(
            hsp.get(
                "hsp_bit_score"
            )
        ),
        experimental_method=str(
            raw_model.get(
                "experimental_method"
            )
            or ""
        ).strip(),
        resolution=optional_float(
            raw_model.get(
                "resolution"
            )
        ),
        coordinate_url=str(
            raw_model.get(
                "model_url"
            )
            or ""
        ).strip(),
        coordinate_format=str(
            raw_model.get(
                "model_format"
            )
            or ""
        ).strip().upper(),
        model_page_url=str(
            raw_model.get(
                "model_page_url"
            )
            or ""
        ).strip(),
        sequence_start=sequence_start,
        sequence_end=sequence_end,
        confidence_type=str(
            raw_model.get(
                "confidence_type"
            )
            or ""
        ).strip(),
        confidence_value=optional_float(
            raw_model.get(
                "confidence_avg_local_score"
            )
        ),
        confidence_version=str(
            raw_model.get(
                "confidence_version"
            )
            or ""
        ).strip(),
        chains=_matched_chains(
            entities,
            sequence_accession,
        ),
        entities=entities,
    )


def normalize_sequence_result(
    payload,
    *,
    query_sequence,
    rows=10,
):
    """
    Normalize an already completed /sequence/result payload.

    This function is deliberately pure and independently
    testable; no network access occurs here.
    """
    query_sequence = (
        _normalize_sequence(
            query_sequence
        )
    )

    rows = _normalize_rows(
        rows
    )

    if not isinstance(
        payload,
        list,
    ):
        raise StructureProviderError(
            "3D-Beacons result payload "
            "must be a list."
        )

    query_length = len(
        query_sequence
    )

    normalized = []
    seen = set()

    for raw_hit in payload:
        if not isinstance(
            raw_hit,
            dict,
        ):
            continue

        summary = raw_hit.get(
            "summary"
        )

        for raw_model in (
            _iter_model_summaries(
                summary
            )
        ):
            try:
                hit = _normalize_model(
                    raw_model,
                    raw_hit=raw_hit,
                    query_length=query_length,
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if (
                hit.canonical_key
                in seen
            ):
                continue

            seen.add(
                hit.canonical_key
            )

            normalized.append(
                hit
            )

    return ProviderSearchBatch(
        provider=key,
        provider_name=display_name,
        query_length=query_length,
        total_count=len(
            normalized
        ),
        hits=tuple(
            normalized[
                :rows
            ]
        ),
    )


def _single_uniprot_identifier(
    entities,
):
    identifiers = []

    for entity in entities:
        if (
            entity.entity_type.upper()
            != "POLYMER"
        ):
            continue

        if (
            entity.identifier_category.upper()
            != "UNIPROT"
        ):
            continue

        identifier = (
            entity.identifier.strip().upper()
        )

        if (
            identifier
            and identifier
            not in identifiers
        ):
            identifiers.append(
                identifier
            )

    if len(
        identifiers
    ) == 1:
        return identifiers[
            0
        ]

    return ""


def _entity_description(
    entities,
    sequence_accession,
):
    sequence_accession = str(
        sequence_accession
        or ""
    ).strip().upper()

    fallback = ""

    for entity in entities:
        if (
            entity.entity_type.upper()
            != "POLYMER"
        ):
            continue

        if (
            not fallback
            and entity.description
        ):
            fallback = (
                entity.description
            )

        if (
            sequence_accession
            and entity.identifier.upper()
            == sequence_accession
            and entity.identifier_category.upper()
            == "UNIPROT"
            and entity.description
        ):
            return entity.description

    return fallback


def get_exact_sequence_summary(
    sequence,
):
    """
    Fetch the synchronous 3D-Beacons structure summary for the
    exact submitted amino-acid sequence.

    The endpoint is checksum/sequence based and does not launch
    a sequence-similarity job.
    """
    sequence = _normalize_sequence(
        sequence
    )

    query = urllib.parse.urlencode(
        {
            "id": sequence,
            "type": "sequence",
        }
    )

    status, payload = _request_json(
        (
            SUMMARY_ENDPOINT
            + "?"
            + query
        )
    )

    if status != 200:
        raise StructureProviderError(
            "Unexpected 3D-Beacons exact "
            f"summary status {status}."
        )

    if not isinstance(
        payload,
        dict,
    ):
        raise StructureProviderError(
            "3D-Beacons exact sequence "
            "summary is not an object."
        )

    structures = payload.get(
        "structures"
    )

    if not isinstance(
        structures,
        list,
    ):
        raise StructureProviderError(
            "3D-Beacons exact sequence "
            "summary has no structures list."
        )

    return payload


def normalize_exact_sequence_summary(
    payload,
    *,
    query_sequence,
    rows=10,
    computational_only=True,
):
    """
    Normalize /sequence/summary.

    Query identity and query coverage are 1.0 by definition:
    this endpoint describes structures registered for the exact
    sequence/checksum rather than homologous sequence hits.

    By default only computational structures are retained.
    Experimental matches remain the responsibility of RCSB in
    the unified default search.
    """
    query_sequence = (
        _normalize_sequence(
            query_sequence
        )
    )

    rows = _normalize_rows(
        rows
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise StructureProviderError(
            "3D-Beacons exact summary payload "
            "must be an object."
        )

    structures = payload.get(
        "structures"
    )

    if not isinstance(
        structures,
        list,
    ):
        raise StructureProviderError(
            "3D-Beacons exact summary payload "
            "has no structures list."
        )

    query_length = len(
        query_sequence
    )

    normalized = []
    seen = set()

    for raw_model in _iter_model_summaries(
        structures
    ):
        try:
            entities = _structure_entities(
                raw_model.get(
                    "entities"
                )
            )

            sequence_accession = (
                _single_uniprot_identifier(
                    entities
                )
            )

            description = (
                _entity_description(
                    entities,
                    sequence_accession,
                )
            )

            synthetic_hit = {
                "accession": sequence_accession,
                "title": description,
                "description": description,
                "hit_hsps": [
                    {
                        "hsp_align_len": (
                            query_length
                        ),
                        "hsp_identity": 100.0,
                        "hsp_bit_score": None,
                    }
                ],
            }

            hit = _normalize_model(
                raw_model,
                raw_hit=synthetic_hit,
                query_length=query_length,
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if (
            computational_only
            and hit.source_type
            != "computational"
        ):
            continue

        if (
            hit.canonical_key
            in seen
        ):
            continue

        seen.add(
            hit.canonical_key
        )

        normalized.append(
            hit
        )

    return ProviderSearchBatch(
        provider=key,
        provider_name=display_name,
        query_length=query_length,
        total_count=len(
            normalized
        ),
        hits=tuple(
            normalized[
                :rows
            ]
        ),
    )


def search_exact_models_by_sequence(
    sequence,
    *,
    rows=10,
):
    """
    Search exact-sequence computational models using the
    synchronous /sequence/summary endpoint.

    No sequence-similarity job and no polling are performed.
    """
    sequence = _normalize_sequence(
        sequence
    )

    rows = _normalize_rows(
        rows
    )

    payload = (
        get_exact_sequence_summary(
            sequence
        )
    )

    return normalize_exact_sequence_summary(
        payload,
        query_sequence=sequence,
        rows=rows,
        computational_only=True,
    )


def search_by_sequence(
    sequence,
    *,
    rows=10,
):
    """
    Bounded synchronous convenience implementation.

    This provider is NOT enabled in DEFAULT_PROVIDERS yet.

    The future HTTP endpoint may use submit/status separately
    instead of holding a Gunicorn worker while an external job
    remains pending.
    """
    sequence = _normalize_sequence(
        sequence
    )

    rows = _normalize_rows(
        rows
    )

    job_id = submit_sequence_search(
        sequence
    )

    for attempt in range(
        POLL_ATTEMPTS
    ):
        state, payload = (
            get_sequence_search_result(
                job_id
            )
        )

        if state == "complete":
            return normalize_sequence_result(
                payload,
                query_sequence=sequence,
                rows=rows,
            )

        if (
            state != "pending"
        ):
            raise StructureProviderError(
                "Unknown 3D-Beacons job state."
            )

        if (
            attempt
            < POLL_ATTEMPTS - 1
        ):
            time.sleep(
                POLL_INTERVAL_SECONDS
            )

    raise StructureProviderError(
        "3D-Beacons sequence search remained "
        "pending beyond the bounded polling window."
    )
