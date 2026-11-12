"""
Server-side geocoding for B3 LIMS.

The browser never contacts the public geocoding provider directly.

Requests are:
- explicit user actions only;
- serialized across local Gunicorn workers;
- rate-limited before upstream access;
- cached on local disk;
- normalized before being returned to the frontend.
"""

import fcntl
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


NOMINATIM_BASE_URL = (
    "https://nominatim.openstreetmap.org"
)

def default_user_agent():
    """Identify the installation to the geocoder (its usage policy asks for contact details)."""
    from django.conf import settings

    contact = str(getattr(settings, "BIOBANK_PUBLIC_URL", "") or "").strip()

    return f"B3-LIMS/1.0 (+{contact})" if contact else "B3-LIMS/1.0"


DEFAULT_USER_AGENT = "B3-LIMS/1.0"

REQUEST_TIMEOUT_SECONDS = 8.0
MIN_REQUEST_INTERVAL_SECONDS = 1.05

SEARCH_CACHE_TTL_SECONDS = 24 * 60 * 60
REVERSE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


class GeocodingUnavailable(Exception):
    """Raised when the upstream geocoder cannot be used."""


def _cache_root():
    root = Path(
        os.environ.get(
            "B3LIMS_GEOCODING_CACHE_DIR",
            "/tmp/b3lims-geocoding-cache",
        )
    )

    root.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    return root


def _cache_path(endpoint, params):
    payload = json.dumps(
        {
            "endpoint": endpoint,
            "params": params,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")

    digest = hashlib.sha256(
        payload
    ).hexdigest()

    return (
        _cache_root()
        / f"{endpoint}-{digest}.json"
    )


def _read_cache(path, ttl_seconds):
    try:
        age = (
            time.time()
            - path.stat().st_mtime
        )

        if age > ttl_seconds:
            return None

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
    ):
        return None


def _write_cache(path, payload):
    temp_path = path.with_name(
        f".{path.name}.{os.getpid()}.tmp"
    )

    temp_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    os.chmod(
        temp_path,
        0o600,
    )

    os.replace(
        temp_path,
        path,
    )


def _serialized_upstream_request(
    endpoint,
    params,
    ttl_seconds,
):
    cache_path = _cache_path(
        endpoint,
        params,
    )

    cached = _read_cache(
        cache_path,
        ttl_seconds,
    )

    if cached is not None:
        return cached

    lock_path = (
        _cache_root()
        / ".nominatim.lock"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock_handle:
        fcntl.flock(
            lock_handle.fileno(),
            fcntl.LOCK_EX,
        )

        # Another Gunicorn worker may have
        # populated the cache while this
        # process was waiting for the lock.
        cached = _read_cache(
            cache_path,
            ttl_seconds,
        )

        if cached is not None:
            return cached

        lock_handle.seek(0)

        try:
            raw_last_request = (
                lock_handle.read().strip()
            )

            last_request = float(
                raw_last_request
            )

        except (
            TypeError,
            ValueError,
        ):
            last_request = 0.0

        now = time.time()

        wait_seconds = max(
            0.0,
            MIN_REQUEST_INTERVAL_SECONDS
            - (now - last_request),
        )

        if wait_seconds:
            time.sleep(
                wait_seconds
            )

        started_at = time.time()

        lock_handle.seek(0)
        lock_handle.truncate()

        lock_handle.write(
            f"{started_at:.6f}"
        )

        lock_handle.flush()

        os.fsync(
            lock_handle.fileno()
        )

        query = urllib.parse.urlencode(
            params
        )

        url = (
            f"{NOMINATIM_BASE_URL}"
            f"/{endpoint}"
            f"?{query}"
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    os.environ.get(
                        "B3LIMS_NOMINATIM_USER_AGENT",
                        default_user_agent(),
                    )
                ),
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                raw = response.read()

            payload = json.loads(
                raw.decode("utf-8")
            )

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise GeocodingUnavailable(
                "The external geocoding service "
                "is temporarily unavailable."
            ) from exc

        _write_cache(
            cache_path,
            payload,
        )

        return payload


def _valid_coordinate_pair(
    lat,
    lon,
):
    try:
        lat_value = float(lat)
        lon_value = float(lon)

    except (
        TypeError,
        ValueError,
    ):
        return None

    if not (
        -90.0 <= lat_value <= 90.0
        and -180.0 <= lon_value <= 180.0
    ):
        return None

    return (
        lat_value,
        lon_value,
    )


def _normalized_address(value):
    if not isinstance(
        value,
        dict,
    ):
        return {}

    normalized = {}

    for key, item in value.items():
        if not isinstance(
            key,
            str,
        ):
            continue

        if not isinstance(
            item,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            continue

        normalized[
            key[:100]
        ] = str(item)[:500]

    return normalized


def _normalize_place(item):
    if not isinstance(
        item,
        dict,
    ):
        return None

    coordinates = (
        _valid_coordinate_pair(
            item.get("lat"),
            item.get("lon"),
        )
    )

    if coordinates is None:
        return None

    display_name = str(
        item.get(
            "display_name",
            "",
        )
    ).strip()

    if not display_name:
        return None

    lat_value, lon_value = (
        coordinates
    )

    result = {
        "display_name": (
            display_name[:1000]
        ),
        # Biobank.location_label
        # currently has max_length=255.
        "label": (
            display_name[:255]
        ),
        "lat": (
            f"{lat_value:.7f}"
        ),
        "lon": (
            f"{lon_value:.7f}"
        ),
        "address": (
            _normalized_address(
                item.get("address")
            )
        ),
    }

    for source_key in (
        "place_id",
        "osm_type",
        "osm_id",
        "category",
        "type",
        "importance",
    ):
        value = item.get(
            source_key
        )

        if value is not None:
            result[
                source_key
            ] = value

    return result


def search_locations(
    query,
    limit=5,
):
    query = " ".join(
        str(
            query or ""
        ).split()
    )

    if len(query) < 3:
        raise ValueError(
            "Search query must contain "
            "at least 3 characters."
        )

    if len(query) > 255:
        raise ValueError(
            "Search query is too long."
        )

    limit = max(
        1,
        min(
            int(limit),
            5,
        ),
    )

    payload = (
        _serialized_upstream_request(
            "search",
            {
                "format": "jsonv2",
                "q": query,
                "addressdetails": "1",
                "dedupe": "1",
                "limit": str(limit),
                "accept-language": (
                    "pt-BR,en"
                ),
            },
            SEARCH_CACHE_TTL_SECONDS,
        )
    )

    if not isinstance(
        payload,
        list,
    ):
        raise GeocodingUnavailable(
            "Unexpected geocoding response."
        )

    results = []

    for item in payload:
        normalized = (
            _normalize_place(
                item
            )
        )

        if normalized is None:
            continue

        results.append(
            normalized
        )

        if len(results) >= limit:
            break

    return results


def reverse_location(
    lat,
    lon,
):
    coordinates = (
        _valid_coordinate_pair(
            lat,
            lon,
        )
    )

    if coordinates is None:
        raise ValueError(
            "Invalid latitude or longitude."
        )

    lat_value, lon_value = (
        coordinates
    )

    payload = (
        _serialized_upstream_request(
            "reverse",
            {
                "format": "jsonv2",
                "lat": (
                    f"{lat_value:.7f}"
                ),
                "lon": (
                    f"{lon_value:.7f}"
                ),
                "zoom": "18",
                "addressdetails": "1",
                "accept-language": (
                    "pt-BR,en"
                ),
            },
            REVERSE_CACHE_TTL_SECONDS,
        )
    )

    result = _normalize_place(
        payload
    )

    if result is None:
        return None

    return result
