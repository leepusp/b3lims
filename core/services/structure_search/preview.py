from __future__ import annotations

import re
from urllib.parse import (
    urljoin,
    urlparse,
)

import requests

from core.services.structure_search.search import (
    DEFAULT_PROVIDERS,
    StructureSearchQueryError,
    _provider_key,
    search_structures_by_sequence,
)


ALLOWED_PREDICTED_COORDINATE_HOSTS = frozenset(
    {
        "alphafold.ebi.ac.uk",
        "swissmodel.expasy.org",
    }
)

MAX_PREDICTED_PREVIEW_BYTES = (
    32 * 1024 * 1024
)

MAX_PREDICTED_PREVIEW_REDIRECTS = 3

PREDICTED_PREVIEW_CONNECT_TIMEOUT_SECONDS = 5
PREDICTED_PREVIEW_READ_TIMEOUT_SECONDS = 30

_REDIRECT_STATUSES = frozenset(
    {
        301,
        302,
        303,
        307,
        308,
    }
)


class StructurePreviewQueryError(
    ValueError
):
    pass


class StructurePreviewFetchError(
    RuntimeError
):
    pass


def _normalize_canonical_key(
    canonical_key,
):
    key = str(
        canonical_key
        or ""
    ).strip()

    if not key:
        raise StructurePreviewQueryError(
            "A predicted-model canonical_key is required."
        )

    if len(key) > 512:
        raise StructurePreviewQueryError(
            "The predicted-model canonical_key is invalid."
        )

    if any(
        character in key
        for character in (
            "\x00",
            "\r",
            "\n",
        )
    ):
        raise StructurePreviewQueryError(
            "The predicted-model canonical_key is invalid."
        )

    return key


def _validated_coordinate_url(
    value,
):
    url = str(
        value
        or ""
    ).strip()

    if not url:
        raise StructurePreviewFetchError(
            "The selected predicted model does not expose "
            "a coordinate file."
        )

    parsed = urlparse(
        url
    )

    if parsed.scheme.lower() != "https":
        raise StructurePreviewFetchError(
            "Predicted-model coordinates must use HTTPS."
        )

    if (
        parsed.username
        or parsed.password
    ):
        raise StructurePreviewFetchError(
            "Predicted-model coordinate URLs cannot contain "
            "embedded credentials."
        )

    host = (
        parsed.hostname
        or ""
    ).lower()

    if (
        host
        not in ALLOWED_PREDICTED_COORDINATE_HOSTS
    ):
        raise StructurePreviewFetchError(
            "The predicted-model coordinate host is not allowed."
        )

    try:
        port = parsed.port

    except ValueError as exc:
        raise StructurePreviewFetchError(
            "The predicted-model coordinate URL has "
            "an invalid port."
        ) from exc

    if port not in (
        None,
        443,
    ):
        raise StructurePreviewFetchError(
            "Predicted-model coordinates must use the "
            "standard HTTPS port."
        )

    return url


def _validate_mmcif_content(
    content,
):
    data = bytes(
        content
        or b""
    )

    stripped = data.lstrip(
        b"\xef\xbb\xbf \t\r\n"
    )

    if not stripped.startswith(
        b"data_"
    ):
        raise StructurePreviewFetchError(
            "The remote coordinate response is not "
            "a valid mmCIF document."
        )

    return data


def _safe_filename(
    accession,
):
    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        str(
            accession
            or ""
        ).strip(),
    ).strip(
        "._"
    )

    if not value:
        value = "predicted-model"

    return (
        value[:160]
        + ".cif"
    )


def _download_mmcif(
    coordinate_url,
    *,
    session=None,
    max_bytes=MAX_PREDICTED_PREVIEW_BYTES,
):
    current_url = (
        _validated_coordinate_url(
            coordinate_url
        )
    )

    own_session = (
        session is None
    )

    if own_session:
        session = requests.Session()

    assert session is not None

    try:
        for redirect_index in range(
            MAX_PREDICTED_PREVIEW_REDIRECTS + 1
        ):
            response = None

            try:
                response = session.get(
                    current_url,
                    headers={
                        "Accept": (
                            "chemical/x-cif,"
                            "application/octet-stream,"
                            "text/plain;q=0.9,"
                            "*/*;q=0.1"
                        ),
                        "User-Agent": (
                            "Biobank-StructurePreview/1"
                        ),
                    },
                    timeout=(
                        PREDICTED_PREVIEW_CONNECT_TIMEOUT_SECONDS,
                        PREDICTED_PREVIEW_READ_TIMEOUT_SECONDS,
                    ),
                    stream=True,
                    allow_redirects=False,
                )

            except requests.RequestException as exc:
                raise StructurePreviewFetchError(
                    "The predicted-model coordinate provider "
                    "could not be reached."
                ) from exc

            try:
                if (
                    response.status_code
                    in _REDIRECT_STATUSES
                ):
                    if (
                        redirect_index
                        >= MAX_PREDICTED_PREVIEW_REDIRECTS
                    ):
                        raise StructurePreviewFetchError(
                            "The predicted-model coordinate request "
                            "exceeded the redirect limit."
                        )

                    location = str(
                        response.headers.get(
                            "Location"
                        )
                        or ""
                    ).strip()

                    if not location:
                        raise StructurePreviewFetchError(
                            "The predicted-model coordinate provider "
                            "returned an invalid redirect."
                        )

                    current_url = (
                        _validated_coordinate_url(
                            urljoin(
                                current_url,
                                location,
                            )
                        )
                    )

                    continue

                if response.status_code not in (
                    200,
                    206,
                ):
                    raise StructurePreviewFetchError(
                        "The predicted-model coordinate provider "
                        f"returned HTTP {response.status_code}."
                    )

                advertised_size = None

                raw_content_length = (
                    response.headers.get(
                        "Content-Length"
                    )
                )

                if raw_content_length:
                    try:
                        advertised_size = int(
                            raw_content_length
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
                    raise StructurePreviewFetchError(
                        "The predicted-model coordinate file "
                        "exceeds the preview size limit."
                    )

                chunks = []
                received = 0

                for chunk in response.iter_content(
                    chunk_size=64 * 1024
                ):
                    if not chunk:
                        continue

                    received += len(
                        chunk
                    )

                    if received > max_bytes:
                        raise StructurePreviewFetchError(
                            "The predicted-model coordinate file "
                            "exceeds the preview size limit."
                        )

                    chunks.append(
                        chunk
                    )

                content = b"".join(
                    chunks
                )

                if not content:
                    raise StructurePreviewFetchError(
                        "The predicted-model coordinate provider "
                        "returned an empty response."
                    )

                return _validate_mmcif_content(
                    content
                )

            finally:
                if response is not None:
                    response.close()

        raise StructurePreviewFetchError(
            "The predicted-model coordinate request failed."
        )

    finally:
        if own_session:
            session.close()


def _exact_computational_provider():
    """
    Return the exact 3D-Beacons provider adapter.

    The Structure Search orchestrator expects provider adapter
    objects, not provider-key strings.
    """

    providers = tuple(
        provider
        for provider in DEFAULT_PROVIDERS
        if _provider_key(
            provider
        )
        == "beacons3d-exact"
    )

    if len(
        providers
    ) != 1:
        raise StructurePreviewFetchError(
            "The exact predicted-structure provider "
            "is not available."
        )

    provider = providers[
        0
    ]

    if not callable(
        getattr(
            provider,
            "search_by_sequence",
            None,
        )
    ):
        raise StructurePreviewFetchError(
            "The exact predicted-structure provider "
            "is invalid."
        )

    return provider


def _find_predicted_hit(
    sequence,
    canonical_key,
):
    key = _normalize_canonical_key(
        canonical_key
    )

    try:
        exact_provider = (
            _exact_computational_provider()
        )

        result = search_structures_by_sequence(
            sequence,
            rows=100,
            providers=(
                exact_provider,
            ),
        )

    except StructureSearchQueryError as exc:
        raise StructurePreviewQueryError(
            str(
                exc
            )
        ) from exc

    payload = result.to_dict()

    hits = payload.get(
        "hits",
        []
    )

    for hit in hits:
        if not isinstance(
            hit,
            dict,
        ):
            continue

        if str(
            hit.get(
                "canonical_key"
            )
            or ""
        ).strip() != key:
            continue

        if str(
            hit.get(
                "source_type"
            )
            or ""
        ).strip().lower() != "computational":
            raise StructurePreviewQueryError(
                "The selected structure is not "
                "a computational model."
            )

        if str(
            hit.get(
                "coordinate_format"
            )
            or ""
        ).strip().lower() != "mmcif":
            raise StructurePreviewFetchError(
                "The selected predicted model is not "
                "available as mmCIF."
            )

        return hit

    raise StructurePreviewQueryError(
        "The selected predicted model is not available "
        "for this Protein sequence."
    )


def fetch_computational_structure_preview(
    sequence,
    canonical_key,
    *,
    session=None,
):
    hit = _find_predicted_hit(
        sequence,
        canonical_key,
    )

    coordinate_url = (
        _validated_coordinate_url(
            hit.get(
                "coordinate_url"
            )
        )
    )

    content = _download_mmcif(
        coordinate_url,
        session=session,
    )

    accession = str(
        hit.get(
            "accession"
        )
        or ""
    ).strip()

    provider = str(
        hit.get(
            "provider"
        )
        or ""
    ).strip()

    provider_name = str(
        hit.get(
            "provider_name"
        )
        or provider
    ).strip()

    return {
        "content":
            content,

        "filename":
            _safe_filename(
                accession
            ),

        "canonical_key":
            str(
                hit.get(
                    "canonical_key"
                )
                or ""
            ).strip(),

        "accession":
            accession,

        "provider":
            provider,

        "provider_name":
            provider_name,

        "coordinate_format":
            "mmcif",
    }
