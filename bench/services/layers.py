"""Layers of the Lab Calendar: the built-in ones and the person's own colours/labels."""

from __future__ import annotations

from bench.models import LayerStyle

BUILTIN = {
    "steps": {
        "label": "My ELN step deadlines",
        "color": "#7c3aed",
        "description": "Unfinished steps with a deadline, from your own experiments.",
    },
    "workflow": {
        "label": "My workflow steps",
        "color": "#d9480f",
        "description": "Unfinished workflow steps with a due date that are yours or in workflows you own.",
    },
    "samples": {
        "label": "Sample events",
        "color": "#198754",
        "description": "Entries, transfers, freezing and QC of samples you can see, grouped by day.",
    },
}


def styles_for(user) -> dict:
    """Effective label/colour/description of each built-in layer for ``user``."""
    saved = {s.key: s for s in LayerStyle.objects.filter(user=user, key__in=BUILTIN)}
    result = {}
    for key, default in BUILTIN.items():
        row = saved.get(key)
        result[key] = {
            "key": key,
            "label": (row and row.label) or default["label"],
            "color": (row and row.color) or default["color"],
            "description": (row and row.description) or default["description"],
            "custom": bool(row and (row.label or row.color or row.description)),
        }
    return result
