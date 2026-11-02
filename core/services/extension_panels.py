"""Extension points that let optional apps add panels to core screens.

Core screens must not import optional apps such as ``bench``. Instead, an app
registers a panel for a named slot (for example ``"notebook_entry.sidebar"``)
from its ``AppConfig.ready()``, and the core template renders whatever is
registered for that slot with the ``extension_panels`` template tag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ContextBuilder = Callable[[Any, Any], "dict | None"]


@dataclass(frozen=True)
class ExtensionPanel:
    """A block of UI contributed to a core screen by another app."""

    slot: str
    key: str
    template: str
    get_context: ContextBuilder
    title: str = ""
    order: int = 100


_REGISTRY: dict[str, dict[str, ExtensionPanel]] = {}


def register_panel(panel: ExtensionPanel) -> None:
    """Register or replace a panel. Re-registering the same key is allowed."""
    if not panel.slot or not panel.key:
        raise ValueError("An extension panel needs a slot and a key.")
    _REGISTRY.setdefault(panel.slot, {})[panel.key] = panel


def unregister_panel(slot: str, key: str) -> None:
    _REGISTRY.get(slot, {}).pop(key, None)


def registered_panels(slot: str) -> list[ExtensionPanel]:
    return sorted(
        _REGISTRY.get(slot, {}).values(),
        key=lambda panel: (panel.order, panel.key),
    )


def panels_for(slot: str, request, obj=None) -> list[dict]:
    """Return the panels to show for ``slot``.

    A panel's ``get_context`` returns ``None`` to hide itself (for example when
    the user may not see its data).
    """
    rendered = []
    for panel in registered_panels(slot):
        context = panel.get_context(request, obj)
        if context is None:
            continue
        rendered.append(
            {
                "key": panel.key,
                "title": panel.title,
                "template": panel.template,
                "context": context,
            }
        )
    return rendered
