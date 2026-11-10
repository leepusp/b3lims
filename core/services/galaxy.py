"""Read-only link with the lab's Galaxy server: its tool catalog, and deep links into it.

Galaxy runs behind Apache with PAM login and trusts the user header only together with a shared secret, so the LIMS
does not log in to it here. The tool list is public inside the machine (the gunicorn behind the proxy answers
anonymously), which is all the catalog needs. Running tools from the LIMS needs per-user identity and is a separate step.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

CACHE_KEY = "biobank.galaxy.tools.v1"
CACHE_SECONDS = 600
TIMEOUT_SECONDS = 6
MAX_BYTES = 6_000_000
MAX_TOOLS = 2000
HIDDEN_SECTIONS = {"Built-in Converters"}


class GalaxyUnavailable(Exception):
    pass


def api_url() -> str:
    return str(getattr(settings, "BIOBANK_GALAXY_API_URL", "http://127.0.0.1:8080/galaxy")).rstrip("/")


def public_path() -> str:
    """Where people reach Galaxy in the browser (same site by default)."""
    return str(getattr(settings, "BIOBANK_GALAXY_PUBLIC_URL", "/galaxy")).rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _fetch_json(path: str):
    base = api_url()

    if not base.startswith(("http://127.0.0.1", "http://localhost", "https://")):
        raise GalaxyUnavailable("The Galaxy API address must be local or https.")

    opener = urllib.request.build_opener(_NoRedirect)

    try:
        with opener.open(urllib.request.Request(base + path, headers={"Accept": "application/json"}), timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GalaxyUnavailable("Galaxy did not answer.") from exc

    if len(body) > MAX_BYTES:
        raise GalaxyUnavailable("Galaxy answered with too much data.")

    try:
        return json.loads(body)
    except ValueError as exc:
        raise GalaxyUnavailable("Galaxy answered something that is not JSON.") from exc


def _text(value, limit) -> str:
    return " ".join(str(value or "").split())[:limit]


def tool_url(tool_id: str) -> str:
    return f"{public_path()}/tool_runner?tool_id={urllib.parse.quote(tool_id, safe='')}"


def _normalise(panel) -> list[dict]:
    """Flat list of tools with their section, from Galaxy's panel structure."""
    tools = []

    def visit(items, section):
        for item in items or []:
            if not isinstance(item, dict) or len(tools) >= MAX_TOOLS:
                continue
            if item.get("model_class") == "ToolSection" or "elems" in item:
                visit(item.get("elems"), _text(item.get("name"), 100) or section)
            elif item.get("id") and item.get("model_class", "Tool") == "Tool" and not item.get("hidden"):
                tool_id = _text(item["id"], 300)
                tools.append({
                    "id": tool_id, "name": _text(item.get("name"), 150) or tool_id, "version": _text(item.get("version"), 40),
                    "description": _text(item.get("description"), 300), "section": section or "Other",
                    "url": tool_url(tool_id), "custom": tool_id.startswith("davinci_"),
                })

    visit(panel, "")

    return [t for t in tools if t["section"] not in HIDDEN_SECTIONS]


def tool_catalog(refresh=False) -> list[dict]:
    """The tools Galaxy offers, cached for a few minutes. Raises GalaxyUnavailable when it cannot be read."""
    if not refresh:
        cached = cache.get(CACHE_KEY)

        if cached is not None:
            return cached

    tools = _normalise(_fetch_json("/api/tools?in_panel=true"))

    if not tools:
        raise GalaxyUnavailable("Galaxy returned no tools.")

    cache.set(CACHE_KEY, tools, CACHE_SECONDS)

    return tools


def find_tool(tool_id: str):
    """One catalog tool by exact id, or None."""
    try:
        return next((t for t in tool_catalog() if t["id"] == tool_id), None)
    except GalaxyUnavailable:
        return None


def resolve_tool(spec: str):
    """The newest tool whose id is ``spec`` or starts with ``spec/`` (a toolshed id without its version)."""
    try:
        tools = tool_catalog()
    except GalaxyUnavailable:
        return None

    matches = [t for t in tools if t["id"] == spec or t["id"].startswith(spec + "/")]

    return sorted(matches, key=lambda t: t["id"])[-1] if matches else None


def clean_result_link(value) -> str:
    """A link to the run in Galaxy: https, or a path on this site. Empty clears it."""
    link = str(value or "").strip()

    if not link:
        return ""
    if len(link) > 300 or any(c in link for c in " <>\"'\\"):
        raise ValidationError("That link is not valid.")
    if link.startswith("https://") or (link.startswith("/") and not link.startswith("//")):
        return link

    raise ValidationError("Use an https link or a path on this site.")
