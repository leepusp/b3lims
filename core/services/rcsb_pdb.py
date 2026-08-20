from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


SEARCH_ENDPOINT = (
    "https://search.rcsb.org/rcsbsearch/v2/query"
)

DATA_ROOT = (
    "https://data.rcsb.org/rest/v1/core"
)

USER_AGENT = (
    "Biobank-MolecularRegistry/2026 "
    "RCSB-PDB-Search"
)

# ==============================================================
# RCSB Search API resilience
# ==============================================================
#
# Sequence-search latency can be substantially higher than the
# RCSB Data API and coordinate CDN.
#
# Keep this policy isolated to the Search API:
#
#   sequence Search API -> 45 s + one transient retry
#   Data API            -> existing 20 s request default
#   coordinate mmCIF    -> existing 30 s download timeout
#
RCSB_SEARCH_TIMEOUT = 45
RCSB_SEARCH_RETRIES = 1

RCSB_TRANSIENT_HTTP_STATUS_CODES = frozenset(
    {
        429,
        502,
        503,
        504,
    }
)

MIN_PROTEIN_LENGTH = 25

PROTEIN_ALPHABET = frozenset(
    "ARNDCEQGHILKMFPSTWYVOUBZX"
)


class RcsbPdbQueryError(
    ValueError
):
    """Raised when the local PDB search query is invalid."""


class RcsbPdbSearchError(
    RuntimeError
):
    """Raised when the remote RCSB service cannot be used."""


def normalize_protein_sequence(
    sequence,
):
    normalized = re.sub(
        r"\s+",
        "",
        str(
            sequence
            or ""
        ).upper(),
    )

    if len(normalized) < MIN_PROTEIN_LENGTH:
        raise RcsbPdbQueryError(
            (
                "PDB sequence search requires "
                f"at least {MIN_PROTEIN_LENGTH} "
                "protein residues."
            )
        )

    invalid = sorted(
        set(
            normalized
        )
        - PROTEIN_ALPHABET
    )

    if invalid:
        raise RcsbPdbQueryError(
            (
                "The Protein sequence contains "
                "characters unsupported by the "
                "RCSB sequence search: "
                + ", ".join(
                    invalid
                )
            )
        )

    return normalized


def _request_json(
    url,
    *,
    payload=None,
    timeout=20,
):
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    data = None
    method = "GET"

    if payload is not None:
        data = json.dumps(
            payload
        ).encode(
            "utf-8"
        )

        headers[
            "Content-Type"
        ] = "application/json"

        method = "POST"

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
                getattr(
                    response,
                    "status",
                    200,
                )
            )

            body = response.read()

    except urllib.error.HTTPError as exc:
        if exc.code == 204:
            return {}

        try:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            detail = ""

        raise RcsbPdbSearchError(
            (
                f"RCSB returned HTTP {exc.code}."
                + (
                    f" {detail[:300]}"
                    if detail
                    else ""
                )
            )
        ) from exc

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise RcsbPdbSearchError(
            (
                "Could not contact the RCSB PDB "
                f"service: {exc}"
            )
        ) from exc

    if status == 204:
        return {}

    if status != 200:
        raise RcsbPdbSearchError(
            f"RCSB returned HTTP {status}."
        )

    try:
        return json.loads(
            body.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise RcsbPdbSearchError(
            "RCSB returned an invalid JSON response."
        ) from exc


def _is_transient_search_error(
    error,
):
    """
    Return True only for remote conditions where one immediate
    Search API retry is useful.

    _request_json() intentionally remains unchanged so Data API
    metadata requests keep their existing behavior.

    RCSB_SEQUENCE_TIMEOUT_HTTP_500_V1_20260816:

    RCSB sequence search can return HTTP 500 when its internal
    sequence-search worker gives up polling a submitted ticket.
    That specific server-side timeout is transient and may be
    retried once.

    Generic HTTP 500 responses remain non-transient.
    """
    message = str(
        error
    )

    if message.startswith(
        "Could not contact the RCSB PDB service:"
    ):
        return True

    if any(
        (
            f"RCSB returned HTTP {status}."
            in message
        )
        for status
        in RCSB_TRANSIENT_HTTP_STATUS_CODES
    ):
        return True

    lower_message = message.lower()

    internal_sequence_timeout = (
        "rcsb returned http 500."
        in lower_message
        and "sequence search server"
        in lower_message
        and (
            "did not complete ticketid"
            in lower_message
            or "giving up polling"
            in lower_message
        )
    )

    if internal_sequence_timeout:
        return True

    return False


def _request_search_json(
    payload,
):
    """
    Perform the RCSB sequence Search API request with its own
    timeout/retry policy.

    The generic _request_json() interface and Data API behavior
    remain unchanged.
    """
    last_error = None

    for attempt in range(
        RCSB_SEARCH_RETRIES + 1
    ):
        try:
            return _request_json(
                SEARCH_ENDPOINT,
                payload=payload,
                timeout=RCSB_SEARCH_TIMEOUT,
            )

        except RcsbPdbSearchError as exc:
            last_error = exc

            if (
                attempt >= RCSB_SEARCH_RETRIES
                or not _is_transient_search_error(
                    exc
                )
            ):
                raise

    #
    # Defensive only. Every normal path above returns or raises.
    #
    if last_error is not None:
        raise last_error

    raise RcsbPdbSearchError(
        "RCSB Search request failed unexpectedly."
    )


def _walk_dicts(
    value,
):
    if isinstance(
        value,
        dict,
    ):
        yield value

        for child in value.values():
            yield from _walk_dicts(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            yield from _walk_dicts(
                child
            )


def _first_number(
    value,
    names,
):
    wanted = {
        str(
            name
        ).lower()
        for name in names
    }

    for item in _walk_dicts(
        value
    ):
        for key, raw in item.items():
            if (
                str(
                    key
                ).lower()
                not in wanted
            ):
                continue

            try:
                number = float(
                    raw
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            return number

    return None


def _first_integer(
    value,
    names,
):
    number = _first_number(
        value,
        names,
    )

    if number is None:
        return None

    return int(
        round(
            number
        )
    )


def _normalize_identity(
    value,
):
    if value is None:
        return None

    identity = float(
        value
    )

    if identity > 1:
        identity /= 100.0

    if identity < 0:
        return None

    return min(
        identity,
        1.0,
    )


def _alignment_metadata(
    hit,
    *,
    query_length,
):
    services = (
        hit.get(
            "services"
        )
        or []
    )

    identity = _normalize_identity(
        _first_number(
            services,
            (
                "sequence_identity",
                "identity",
                "identity_fraction",
                "identity_percent",
            ),
        )
    )

    evalue = _first_number(
        services,
        (
            "evalue",
            "e_value",
            "expect",
        ),
    )

    bitscore = _first_number(
        services,
        (
            "bitscore",
            "bit_score",
            "bit-score",
        ),
    )

    query_start = _first_integer(
        services,
        (
            "query_beg",
            "query_begin",
            "query_start",
            "query_from",
        ),
    )

    query_end = _first_integer(
        services,
        (
            "query_end",
            "query_stop",
            "query_to",
        ),
    )

    subject_start = _first_integer(
        services,
        (
            "subject_beg",
            "subject_begin",
            "subject_start",
            "target_beg",
            "target_begin",
            "target_start",
        ),
    )

    subject_end = _first_integer(
        services,
        (
            "subject_end",
            "subject_stop",
            "target_end",
            "target_stop",
        ),
    )

    query_coverage = None

    if (
        query_start is not None
        and query_end is not None
        and query_length > 0
    ):
        aligned = (
            abs(
                query_end
                - query_start
            )
            + 1
        )

        query_coverage = min(
            1.0,
            aligned
            / query_length,
        )

    return {
        "identity": identity,
        "evalue": evalue,
        "bitscore": bitscore,
        "query_start": query_start,
        "query_end": query_end,
        "subject_start": subject_start,
        "subject_end": subject_end,
        "query_coverage": (
            query_coverage
        ),
    }


def _parse_entity_identifier(
    identifier,
):
    match = re.fullmatch(
        r"([A-Za-z0-9]+)_([A-Za-z0-9]+)",
        str(
            identifier
            or ""
        ).strip(),
    )

    if not match:
        raise RcsbPdbSearchError(
            (
                "Unexpected RCSB polymer-entity "
                f"identifier: {identifier!r}"
            )
        )

    return (
        match.group(1).upper(),
        match.group(2),
    )


def _canonical_sequence_length(
    polymer_payload,
):
    entity_poly = (
        polymer_payload.get(
            "entity_poly"
        )
        or {}
    )

    sequence = re.sub(
        r"\s+",
        "",
        str(
            entity_poly.get(
                "pdbx_seq_one_letter_code_can",
                "",
            )
            or ""
        ),
    )

    return len(
        sequence
    )


def _polymer_metadata(
    pdb_id,
    entity_id,
):
    payload = _request_json(
        (
            f"{DATA_ROOT}/polymer_entity/"
            f"{pdb_id}/{entity_id}"
        )
    )

    identifiers = (
        payload.get(
            "rcsb_polymer_entity_container_identifiers"
        )
        or {}
    )

    polymer = (
        payload.get(
            "rcsb_polymer_entity"
        )
        or {}
    )

    chains = (
        identifiers.get(
            "auth_asym_ids"
        )
        or identifiers.get(
            "asym_ids"
        )
        or []
    )

    return {
        "description": str(
            polymer.get(
                "pdbx_description"
            )
            or ""
        ),
        "chains": [
            str(
                chain
            )
            for chain in chains
        ],
        "entity_sequence_length": (
            _canonical_sequence_length(
                payload
            )
        ),
    }


def _entry_metadata(
    pdb_id,
):
    payload = _request_json(
        (
            f"{DATA_ROOT}/entry/"
            f"{pdb_id}"
        )
    )

    entry_info = (
        payload.get(
            "rcsb_entry_info"
        )
        or {}
    )

    struct = (
        payload.get(
            "struct"
        )
        or {}
    )

    exptl = (
        payload.get(
            "exptl"
        )
        or []
    )

    methods = []

    for item in exptl:
        if not isinstance(
            item,
            dict,
        ):
            continue

        method = str(
            item.get(
                "method"
            )
            or ""
        ).strip()

        if (
            method
            and method not in methods
        ):
            methods.append(
                method
            )

    method_summary = str(
        entry_info.get(
            "experimental_method"
        )
        or ""
    ).strip()

    if not method_summary:
        method_summary = ", ".join(
            methods
        )

    resolution = None

    for value in (
        entry_info.get(
            "resolution_combined"
        )
        or []
    ):
        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if (
            resolution is None
            or number < resolution
        ):
            resolution = number

    methodology = str(
        entry_info.get(
            "structure_determination_methodology"
        )
        or ""
    ).strip().lower()

    return {
        "title": str(
            struct.get(
                "title"
            )
            or ""
        ),
        "experimental_method": (
            method_summary
        ),
        "resolution": resolution,
        "methodology": methodology,
    }


def _enrich_hit(
    hit,
    *,
    query_length,
):
    identifier = str(
        hit.get(
            "identifier"
        )
        or ""
    )

    pdb_id, entity_id = (
        _parse_entity_identifier(
            identifier
        )
    )

    alignment = (
        _alignment_metadata(
            hit,
            query_length=query_length,
        )
    )

    polymer = {
        "description": "",
        "chains": [],
        "entity_sequence_length": None,
    }

    entry = {
        "title": "",
        "experimental_method": "",
        "resolution": None,
        "methodology": "",
    }

    warnings = []

    try:
        polymer = _polymer_metadata(
            pdb_id,
            entity_id,
        )
    except RcsbPdbSearchError as exc:
        warnings.append(
            f"polymer metadata: {exc}"
        )

    try:
        entry = _entry_metadata(
            pdb_id
        )
    except RcsbPdbSearchError as exc:
        warnings.append(
            f"entry metadata: {exc}"
        )

    return {
        "identifier": identifier,
        "pdb_id": pdb_id,
        "entity_id": entity_id,
        "score": hit.get(
            "score"
        ),
        **alignment,
        **polymer,
        **entry,
        "warnings": warnings,
    }


def search_pdb_by_sequence(
    sequence,
    *,
    identity_cutoff=0.90,
    evalue_cutoff=0.1,
    rows=10,
):
    sequence = (
        normalize_protein_sequence(
            sequence
        )
    )

    try:
        identity_cutoff = float(
            identity_cutoff
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise RcsbPdbQueryError(
            "Invalid sequence identity cutoff."
        ) from exc

    if not (
        0.30
        <= identity_cutoff
        <= 1.0
    ):
        raise RcsbPdbQueryError(
            (
                "Sequence identity cutoff must "
                "be between 0.30 and 1.00."
            )
        )

    try:
        evalue_cutoff = float(
            evalue_cutoff
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise RcsbPdbQueryError(
            "Invalid E-value cutoff."
        ) from exc

    if not (
        0
        < evalue_cutoff
        <= 100
    ):
        raise RcsbPdbQueryError(
            (
                "E-value cutoff must be greater "
                "than 0 and at most 100."
            )
        )

    try:
        rows = int(
            rows
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise RcsbPdbQueryError(
            "Invalid result-count limit."
        ) from exc

    if not (
        1
        <= rows
        <= 20
    ):
        raise RcsbPdbQueryError(
            (
                "Result-count limit must be "
                "between 1 and 20."
            )
        )

    request_payload = {
        "query": {
            "type": "terminal",
            "service": "sequence",
            "parameters": {
                "evalue_cutoff": (
                    evalue_cutoff
                ),
                "identity_cutoff": (
                    identity_cutoff
                ),
                "sequence_type": "protein",
                "value": sequence,
            },
        },
        "request_options": {
            "scoring_strategy": "sequence",
            "results_verbosity": "verbose",
            "results_content_type": [
                "experimental",
            ],
            "paginate": {
                "start": 0,
                "rows": rows,
            },
        },
        "return_type": "polymer_entity",
    }

    search_payload = _request_search_json(
        request_payload
    )

    raw_hits = (
        search_payload.get(
            "result_set"
        )
        or []
    )

    hits = []

    for raw_hit in raw_hits:
        if not isinstance(
            raw_hit,
            dict,
        ):
            continue

        try:
            hit = _enrich_hit(
                raw_hit,
                query_length=len(
                    sequence
                ),
            )

        except RcsbPdbSearchError:
            continue

        # Defensive filtering.
        #
        # Search itself requests experimental-only
        # content. If the Data API explicitly reports
        # another methodology, do not expose it in the
        # experimental PDB finder.
        if (
            hit.get(
                "methodology"
            )
            and hit[
                "methodology"
            ] != "experimental"
        ):
            continue

        hits.append(
            hit
        )

    return {
        "query_length": len(
            sequence
        ),
        "identity_cutoff": (
            identity_cutoff
        ),
        "evalue_cutoff": (
            evalue_cutoff
        ),
        "requested_rows": rows,
        "total_count": int(
            search_payload.get(
                "total_count"
            )
            or 0
        ),
        "hits": hits,
    }


# ==============================================================
# RCSB coordinate preview
# ==============================================================

RCSB_FILES_ROOT = (
    "https://files.rcsb.org/download"
)

MAX_PDB_PREVIEW_BYTES = (
    50
    * 1024
    * 1024
)


def normalize_pdb_id(
    pdb_id,
):
    normalized = str(
        pdb_id
        or ""
    ).strip().upper()

    if not re.fullmatch(
        r"[A-Z0-9]{4}",
        normalized,
    ):
        raise RcsbPdbQueryError(
            "Invalid four-character PDB identifier."
        )

    return normalized


def fetch_pdb_mmcif(
    pdb_id,
    *,
    timeout=30,
    max_bytes=MAX_PDB_PREVIEW_BYTES,
):
    """
    Retrieve one RCSB PDB entry as mmCIF for temporary preview.

    User input controls only a validated four-character PDB ID.
    The remote host is fixed by this service.

    No file is persisted here.
    """

    pdb_id = normalize_pdb_id(
        pdb_id
    )

    url = (
        f"{RCSB_FILES_ROOT}/"
        f"{pdb_id}.cif"
    )

    request = urllib.request.Request(
        url,
        headers={
            "Accept": (
                "chemical/x-cif,"
                "text/plain;q=0.9,"
                "*/*;q=0.1"
            ),
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            status = int(
                getattr(
                    response,
                    "status",
                    200,
                )
            )

            if status != 200:
                raise RcsbPdbSearchError(
                    (
                        "RCSB coordinate download "
                        f"returned HTTP {status}."
                    )
                )

            content_length = (
                response.headers.get(
                    "Content-Length"
                )
            )

            if content_length:
                try:
                    advertised_size = int(
                        content_length
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    advertised_size = None

                if (
                    advertised_size is not None
                    and advertised_size > max_bytes
                ):
                    raise RcsbPdbSearchError(
                        (
                            "The selected PDB coordinate "
                            "file is too large for browser "
                            "preview."
                        )
                    )

            content = response.read(
                max_bytes + 1
            )

    except urllib.error.HTTPError as exc:
        raise RcsbPdbSearchError(
            (
                "Could not retrieve the selected "
                f"PDB entry (HTTP {exc.code})."
            )
        ) from exc

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise RcsbPdbSearchError(
            (
                "Could not retrieve the selected "
                f"PDB entry: {exc}"
            )
        ) from exc

    if len(
        content
    ) > max_bytes:
        raise RcsbPdbSearchError(
            (
                "The selected PDB coordinate file "
                "is too large for browser preview."
            )
        )

    if not content:
        raise RcsbPdbSearchError(
            "RCSB returned an empty coordinate file."
        )

    if not content.lstrip().startswith(
        b"data_"
    ):
        raise RcsbPdbSearchError(
            (
                "RCSB returned a coordinate file "
                "that is not valid mmCIF."
            )
        )

    if b"_atom_site." not in content:
        raise RcsbPdbSearchError(
            (
                "The RCSB mmCIF file does not "
                "contain an atom-site table."
            )
        )

    return {
        "pdb_id": pdb_id,
        "filename": (
            f"{pdb_id}.cif"
        ),
        "content": content,
        "size_bytes": len(
            content
        ),
    }
