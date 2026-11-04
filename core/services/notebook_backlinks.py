"""Backlinks from LIMS entities to the ELN entries that cite them.

The ELN already stores explicit links (samples, reagents, molecular records,
Jupyter notebooks) and @-mentions. This module reads them from the entity side
so that a sample, reagent, molecular record or Jupyter notebook can show
"Used in experiments". Only entries the viewer may see are returned.
"""
from __future__ import annotations

from core.permissions.notebook import visible_notebook_entries_for_user

LIMIT = 50


def _collect(rows, user, via):
    """rows: iterable of (entry_id, when, notes). Returns visible entries."""
    rows = list(rows)
    if not rows:
        return []
    visible = visible_notebook_entries_for_user(user).filter(
        pk__in={r[0] for r in rows}
    ).select_related("author")
    by_id = {e.pk: e for e in visible}
    out = []
    for entry_id, when, notes in rows:
        entry = by_id.get(entry_id)
        if entry is None:
            continue
        out.append({"entry": entry, "via": via, "when": when, "notes": notes or ""})
    return out


def _merge(*groups):
    seen, merged = {}, []
    for group in groups:
        for item in group:
            pk = item["entry"].pk
            if pk in seen:
                seen[pk]["via"] = f'{seen[pk]["via"]}, {item["via"]}'
                continue
            seen[pk] = item
            merged.append(item)
    merged.sort(key=lambda i: i["when"] or i["entry"].updated_at, reverse=True)
    return merged[:LIMIT]


def entries_for_sample(user, sample):
    links = sample.notebook_sample_links.values_list("entry_id", "linked_at", "notes")
    mentions = [
        (e.pk, e.updated_at, "")
        for e in sample.notebook_mentions.only("pk", "updated_at")
    ]
    return _merge(_collect(links, user, "linked"), _collect(mentions, user, "mentioned"))


def entries_for_chemical(user, chemical):
    links = chemical.notebook_chemical_links.values_list("entry_id", "linked_at", "notes")
    return _merge(_collect(links, user, "linked"))


def entries_for_molecule(user, molecule):
    links = molecule.notebook_links.values_list("entry_id", "linked_at", "notes")
    groups = [_collect(links, user, "linked")]
    if molecule.source_entry_id:
        groups.append(
            _collect(
                [(molecule.source_entry_id, molecule.created_at, "")],
                user,
                "created in",
            )
        )
    return _merge(*groups)


def entries_for_jupyter(user, notebook):
    links = notebook.eln_links.values_list("entry_id", "linked_at")
    return _merge(_collect(((a, b, "") for a, b in links), user, "linked"))


RESOLVERS = {
    "sample": entries_for_sample,
    "chemical": entries_for_chemical,
    "molecule": entries_for_molecule,
    "jupyter": entries_for_jupyter,
}
