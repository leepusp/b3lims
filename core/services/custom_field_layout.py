"""Where an entry keeps its custom fields inside ``NotebookEntry.metadata``.

Current layout (also used by ``NotebookTemplate.structure``):

    {
      "custom_fields": {"Medium": {"type": "select", "value": "TSB", ...}},
      "custom_field_groups": [{"id": 1, "name": "Culture"}]
    }

Earlier releases stored the same data under ``extra_fields`` and
``elabftw.extra_fields_groups``. The rename is done in two releases
(expand, then contract) so a rollback never meets data it cannot read:

* expand (now): readers prefer the new keys and fall back to the old ones;
  writers store both. A data migration copies existing rows.
* contract (later): stop writing and drop the old keys, once the previous
  release is no longer a rollback target.
"""

import copy

FIELDS_KEY = "custom_fields"
GROUPS_KEY = "custom_field_groups"

LEGACY_FIELDS_KEY = "extra_fields"
LEGACY_NAMESPACE = "elabftw"
LEGACY_GROUPS_KEY = "extra_fields_groups"

# Flip to False in the contract release.
WRITE_LEGACY_KEYS = True


def _dict(data):
    return data if isinstance(data, dict) else {}


def fields_of(data):
    data = _dict(data)
    if isinstance(data.get(FIELDS_KEY), dict):
        return data[FIELDS_KEY]
    legacy = data.get(LEGACY_FIELDS_KEY)
    return legacy if isinstance(legacy, dict) else {}


def groups_of(data):
    data = _dict(data)
    if isinstance(data.get(GROUPS_KEY), list):
        return data[GROUPS_KEY]
    legacy = _dict(data.get(LEGACY_NAMESPACE)).get(LEGACY_GROUPS_KEY)
    return legacy if isinstance(legacy, list) else []


def has_fields(data):
    return bool(fields_of(data))


def with_layout(base, fields, groups):
    """Copy of ``base`` carrying ``fields`` and ``groups`` in every stored key."""
    result = dict(_dict(base))
    result[FIELDS_KEY] = fields
    result[GROUPS_KEY] = groups
    if WRITE_LEGACY_KEYS:
        result[LEGACY_FIELDS_KEY] = copy.deepcopy(fields)
        namespace = dict(_dict(result.get(LEGACY_NAMESPACE)))
        namespace[LEGACY_GROUPS_KEY] = copy.deepcopy(groups)
        result[LEGACY_NAMESPACE] = namespace
    else:
        result.pop(LEGACY_FIELDS_KEY, None)
        namespace = dict(_dict(result.get(LEGACY_NAMESPACE)))
        namespace.pop(LEGACY_GROUPS_KEY, None)
        if namespace:
            result[LEGACY_NAMESPACE] = namespace
        else:
            result.pop(LEGACY_NAMESPACE, None)
    return result


def migrated(data):
    """``data`` in the current layout, or None when it needs no change.

    Idempotent: data that already has the new keys is returned as None, so it
    can be run again after a rollback window without overwriting newer edits
    unless ``force`` semantics are wanted (see ``migrated_forced``).
    """
    data = _dict(data)
    has_legacy = LEGACY_FIELDS_KEY in data or LEGACY_GROUPS_KEY in _dict(data.get(LEGACY_NAMESPACE))
    if not has_legacy:
        return None
    if FIELDS_KEY in data and GROUPS_KEY in data:
        return None
    return with_layout(data, copy.deepcopy(fields_of(data)), copy.deepcopy(groups_of(data)))


def migrated_forced(data):
    """Like ``migrated`` but the old keys win (used after a rollback)."""
    data = _dict(data)
    legacy_fields = data.get(LEGACY_FIELDS_KEY)
    legacy_groups = _dict(data.get(LEGACY_NAMESPACE)).get(LEGACY_GROUPS_KEY)
    if legacy_fields is None and legacy_groups is None:
        return None
    fields = legacy_fields if isinstance(legacy_fields, dict) else fields_of(data)
    groups = legacy_groups if isinstance(legacy_groups, list) else groups_of(data)
    result = with_layout(data, copy.deepcopy(fields), copy.deepcopy(groups))
    return None if result == data else result
