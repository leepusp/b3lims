"""Sample types an installation defines for itself, next to the four built-in ones.

A custom type has a name, an ID prefix and a list of extra fields. Registering a Sample of that type stores
the values in ``Sample.type_data``. The built-in types keep their own tables and are not listed here.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils.text import slugify

BUILTIN_TYPES = ("Bacterium (Host)", "Phage (Virus)", "Plasmid", "Other")
KINDS = ("text", "integer", "decimal", "boolean", "choice", "date")
FIELD_HELP = (
    "One field per line: Label | kind | required | choices\n"
    "kind is text, integer, decimal, boolean, choice or date (text when left out). "
    "Write 'required' to make the field compulsory. For choice, list the options separated by commas.\n"
    "Example:  Mycoplasma status | choice | required | negative, positive, untested"
)


class SampleTypeError(ValueError):
    pass


def custom_types(active_only=True):
    from core.models.samples.sample_type import SampleType

    queryset = SampleType.objects.all()

    return queryset.filter(is_active=True) if active_only else queryset


def get_custom(name):
    return custom_types().filter(name=name).first() if name else None


def all_type_names():
    return list(BUILTIN_TYPES[:3]) + [t.name for t in custom_types()] + [BUILTIN_TYPES[3]]


def id_prefixes():
    """Prefix of every custom type, for the ID generator in the New Sample form."""
    return {t.name: t.id_prefix for t in custom_types()}


def reserved_keys():
    """Names a custom field may not use because a built-in column already means something else."""
    from core.services import sample_tables
    from core.services.sample_intake import COLUMN_ALIASES

    builtin = sample_tables.COMMON + sample_tables.BACTERIUM_COLUMNS + sample_tables.PHAGE_COLUMNS + sample_tables.PLASMID_COLUMNS

    return {c.key for c in builtin} | set(COLUMN_ALIASES) | {"collection", "collections", "status", "tags", "keywords", "notes"}


def parse_fields(text):
    """Turn the lines typed by an administrator into the stored field list; raise SampleTypeError on a mistake."""
    fields, seen = [], set()

    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()

        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]
        label = parts[0]
        kind = (parts[1].lower() if len(parts) > 1 and parts[1] else "text")
        required = len(parts) > 2 and parts[2].lower() in {"required", "yes", "true", "1", "*"}
        choices = [c.strip() for c in parts[3].split(",") if c.strip()] if len(parts) > 3 else []
        key = re.sub(r"[^a-z0-9]+", "_", slugify(label).replace("-", "_")).strip("_")

        if not label or not key:
            raise SampleTypeError(f"Line {number}: the field needs a name.")

        if kind not in KINDS:
            raise SampleTypeError(f"Line {number}: kind '{kind}' is not one of {', '.join(KINDS)}.")

        if kind == "choice" and not choices:
            raise SampleTypeError(f"Line {number}: a choice field needs its options (fourth column).")

        if key in seen:
            raise SampleTypeError(f"Line {number}: '{label}' repeats another field.")

        seen.add(key)
        fields.append({"key": key, "label": label, "kind": kind, "required": required, "choices": choices})

    return fields


def fields_to_text(fields):
    lines = []

    for f in fields or []:
        lines.append(" | ".join([
            f["label"], f.get("kind", "text"), "required" if f.get("required") else "", ", ".join(f.get("choices") or []),
        ]).rstrip(" |"))

    return "\n".join(lines)


def read_values(sample_type, post):
    """Read and check ``tf_<key>`` values of a submitted form; return the dict to store in ``type_data``."""
    values = {}

    for f in sample_type.fields or []:
        raw = (post.get(f"tf_{f['key']}") or "").strip()
        label = f["label"]

        if not raw:
            if f.get("required"):
                raise SampleTypeError(f"{label} is required for {sample_type.name}.")

            continue

        kind = f.get("kind", "text")

        try:
            if kind == "integer":
                raw = int(raw)
            elif kind == "decimal":
                raw = float(Decimal(raw.replace(",", ".")))
            elif kind == "date":
                date.fromisoformat(raw)
            elif kind == "boolean":
                raw = raw.lower() in {"1", "true", "yes", "on", "sim"}
            elif kind == "choice" and raw not in f.get("choices", []):
                raise SampleTypeError(f"{label}: choose one of {', '.join(f['choices'])}.")
        except (ValueError, InvalidOperation) as exc:
            raise SampleTypeError(f"{label}: '{raw}' is not a valid {kind}.") from exc

        values[f["key"]] = raw

    return values


def describe(sample):
    """(label, value) pairs of a Sample's extra fields, in the order of its type."""
    data = getattr(sample, "type_data", None) or {}

    if not data:
        return []

    custom = custom_types(active_only=False).filter(name=sample.sample_type).first()
    labels = {f["key"]: f["label"] for f in (custom.fields if custom else [])}

    return [(labels.get(k, k), v) for k, v in data.items()]
