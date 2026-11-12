"""Read-only eLabFTW REST API v2 client.

No global credentials, no public endpoint, no redirects,
no direct database access, and no automatic network calls.
"""

import http.client
import json
import socket
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings


class ElnApiError(Exception):
    """Unexpected or invalid API response."""


class ElnUnauthorized(ElnApiError):
    """API credentials rejected."""


class ElnForbidden(ElnApiError):
    """API account lacks permission."""


class ElnUnavailable(ElnApiError):
    """API unavailable or transport failed."""


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTP connection over a local Unix domain socket."""

    def __init__(self, socket_path, timeout):
        super().__init__(
            host=getattr(settings, "BIOBANK_ELN_API_HOST", "localhost"),
            port=80,
            timeout=timeout,
        )
        self.socket_path = str(socket_path)

    def connect(self):
        connection = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        connection.settimeout(self.timeout)

        try:
            connection.connect(self.socket_path)
        except Exception:
            connection.close()
            raise

        self.sock = connection


class UnixSocketTransport:
    """Transport for a separately managed private relay."""

    def __init__(self, socket_path):
        path = Path(socket_path)

        if not path.is_absolute():
            raise ValueError(
                "The ELN socket path must be absolute."
            )

        self.socket_path = path

    def get(
        self,
        path,
        api_key,
        timeout,
        max_bytes,
    ):
        connection = UnixHTTPConnection(
            self.socket_path,
            timeout,
        )

        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Authorization": api_key,
                    "Accept": "application/json",
                    "X-Forwarded-Proto": "https",
                    "Cache-Control": "no-store",
                    "Connection": "close",
                },
            )

            response = connection.getresponse()

            status = response.status
            content_type = response.getheader(
                "Content-Type",
                "",
            )

            payload = response.read(max_bytes + 1)

            if len(payload) > max_bytes:
                raise ElnApiError(
                    "The ELN response exceeds the size limit."
                )

            return status, content_type, payload

        except (
            OSError,
            TimeoutError,
            http.client.HTTPException,
        ) as exc:
            raise ElnUnavailable(
                "The internal ELN API is unavailable."
            ) from None

        finally:
            connection.close()


class ElnReadOnlyClient:
    """Authenticated read-only eLabFTW API client."""

    def __init__(
        self,
        *,
        api_key,
        transport,
        timeout=3,
        max_bytes=524288,
    ):
        if (
            not isinstance(api_key, str)
            or not api_key
            or len(api_key) > 4096
            or any(ch.isspace() for ch in api_key)
        ):
            raise ValueError("Invalid ELN credential.")

        if not callable(getattr(transport, "get", None)):
            raise TypeError(
                "An explicit API transport is required."
            )

        if not 0 < timeout <= 10:
            raise ValueError("Invalid API timeout.")

        if not 1024 <= max_bytes <= 4194304:
            raise ValueError("Invalid response size limit.")

        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._max_bytes = max_bytes

    def _fetch(self, path, expected_type):
        status, content_type, payload = (
            self._transport.get(
                path,
                self._api_key,
                self._timeout,
                self._max_bytes,
            )
        )

        if status == 401:
            raise ElnUnauthorized(
                "ELN API authentication failed."
            )

        if status == 403:
            raise ElnForbidden(
                "ELN API access denied."
            )

        if status >= 500 or status == 429:
            raise ElnUnavailable(
                "ELN API temporarily unavailable."
            )

        if status != 200:
            raise ElnApiError(
                f"Unexpected ELN HTTP status: {status}."
            )

        if not content_type.lower().startswith(
            "application/json"
        ):
            raise ElnApiError(
                "Unexpected ELN response content type."
            )

        try:
            result = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise ElnApiError(
                "Invalid ELN JSON response."
            ) from None

        if not isinstance(result, expected_type):
            raise ElnApiError(
                "Unexpected ELN response structure."
            )

        return result

    @staticmethod
    def _pagination(limit, offset):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("Invalid page limit.")

        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= 1000000
        ):
            raise ValueError("Invalid page offset.")

        return urlencode({
            "limit": limit,
            "offset": offset,
        })

    def list_experiments(self, limit=25, offset=0):
        query = self._pagination(limit, offset)

        return self._fetch(
            f"/api/v2/experiments?{query}",
            list,
        )

    def list_templates(self, limit=25, offset=0):
        query = self._pagination(limit, offset)

        return self._fetch(
            f"/api/v2/experiments_templates?{query}",
            list,
        )

    def get_experiment(self, experiment_id):
        if (
            isinstance(experiment_id, bool)
            or not isinstance(experiment_id, int)
            or experiment_id <= 0
        ):
            raise ValueError(
                "Invalid ELN experiment identifier."
            )

        return self._fetch(
            f"/api/v2/experiments/{experiment_id}",
            dict,
        )
