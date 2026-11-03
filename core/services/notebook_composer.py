"""Rules for the composable parts of a Notebook entry (B3 Bench 1.A).

Custom fields follow eLabFTW's metadata layout so they can be exported
to .eln unchanged:

    {
      "extra_fields": {
        "Medium": {"type": "select", "value": "TSB", "options": [...],
                   "required": true, "group_id": 1, "position": 0, ...}
      },
      "elabftw": {"extra_fields_groups": [{"id": 1, "name": "Culture"}]}
    }

Reference fields store the id of the referenced record; every id is
checked against what the editing user is allowed to see.
"""

import re
from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from django.utils import timezone

from core.models.lab_tools.notebook_composer import (
    NotebookEntryLink,
    NotebookStep,
    NotebookTag,
)


FIELD_TYPES = {
    "text": "Text",
    "number": "Number",
    "select": "Dropdown menu",
    "radio": "Radio buttons",
    "checkbox": "Checkbox",
    "date": "Date",
    "datetime-local": "Date and time",
    "time": "Time",
    "email": "Email",
    "url": "URL",
    "items": "Sample",
    "compounds": "Reagent / compound",
    "experiments": "Notebook entry",
    "users": "User",
    "uploads": "Attached file",
}

REFERENCE_TYPES = {"items", "compounds", "experiments", "users", "uploads"}
CHOICE_TYPES = {"select", "radio"}

MAX_FIELDS = 100
MAX_GROUPS = 30
MAX_OPTIONS = 100
MAX_TEXT = 5000
MAX_STEPS = 200
MAX_TAGS = 30
MAX_LINKS = 100

TAG_RE = re.compile(r"^[\w .+#/:-]{1,64}$")
CUSTOM_ID_RE = re.compile(r"^[\w .:/#-]{0,64}$")

_url_validator = URLValidator(schemes=["http", "https"])


def _text(value, limit, label):
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise ValidationError(f"{label}: must be text.")
    value = str(value).strip()
    if len(value) > limit:
        raise ValidationError(f"{label}: too long (max {limit}).")
    return value


def _string_list(values, label, limit=MAX_OPTIONS):
    if values in (None, ""):
        return []
    if not isinstance(values, list) or len(values) > limit:
        raise ValidationError(f"{label}: must be a list of at most {limit} items.")
    result = []
    for value in values:
        value = _text(value, 200, label)
        if value and value not in result:
            result.append(value)
    return result


# --- reference lookups -------------------------------------------------------


def _visible_samples(user):
    from core.permissions.samples import visible_samples_for_user

    return visible_samples_for_user(user)


def _visible_chemicals(user):
    from core.permissions.chemicals import visible_chemicals_for_user

    return visible_chemicals_for_user(user)


def _visible_entries(user):
    from core.permissions.notebook import visible_notebook_entries_for_user

    return visible_notebook_entries_for_user(user)


def _active_users():
    return get_user_model().objects.filter(is_active=True)


def reference_queryset(kind, user, entry=None):
    if kind == "items":
        return _visible_samples(user)
    if kind == "compounds":
        return _visible_chemicals(user)
    if kind == "experiments":
        return _visible_entries(user)
    if kind == "users":
        return _active_users()
    if kind == "uploads":
        if entry is None:
            raise ValueError("uploads require an entry")
        return entry.attachments.all()
    raise ValueError(f"unknown reference kind: {kind}")


def reference_label(kind, obj):
    if kind == "items":
        return f"{obj.sample_id} · {obj.organism_name or obj.sample_type or ''}".strip(" ·")
    if kind == "compounds":
        cas = f" · CAS {obj.cas_number}" if getattr(obj, "cas_number", "") else ""
        return f"{obj.name}{cas}"
    if kind == "experiments":
        prefix = f"{obj.custom_id} · " if obj.custom_id else f"#{obj.pk} · "
        return f"{prefix}{obj.title}"
    if kind == "users":
        full = obj.get_full_name() if hasattr(obj, "get_full_name") else ""
        return f"{full} ({obj.get_username()})" if full else obj.get_username()
    if kind == "uploads":
        return obj.original_filename or obj.caption or f"File {obj.pk}"
    return str(obj)


def search_references(kind, user, query, entry=None, limit=15):
    from django.db.models import Q

    qs = reference_queryset(kind, user, entry)
    query = (query or "").strip()

    if query:
        if kind == "items":
            qs = qs.filter(
                Q(sample_id__icontains=query)
                | Q(organism_name__icontains=query)
                | Q(sample_type__icontains=query)
            )
        elif kind == "compounds":
            qs = qs.filter(Q(name__icontains=query) | Q(cas_number__icontains=query))
        elif kind == "experiments":
            qs = qs.filter(Q(title__icontains=query) | Q(custom_id__icontains=query))
            if query.lstrip("#").isdigit():
                qs = qs | reference_queryset(kind, user).filter(pk=int(query.lstrip("#")))
        elif kind == "users":
            qs = qs.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
        elif kind == "uploads":
            qs = qs.filter(Q(original_filename__icontains=query) | Q(caption__icontains=query))

    if kind == "experiments" and entry is not None:
        qs = qs.exclude(pk=entry.pk)

    return [
        {"id": obj.pk, "label": reference_label(kind, obj)}
        for obj in qs.distinct()[:limit]
    ]


def _validate_reference(kind, value, user, entry):
    if value in ("", None):
        return ""
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {FIELD_TYPES[kind].lower()} reference.")
    if not reference_queryset(kind, user, entry).filter(pk=pk).exists():
        raise ValidationError(
            f"{FIELD_TYPES[kind]} {pk} does not exist or is not visible to you."
        )
    return str(pk)


# --- custom fields ------------------------------------------------------------


def _validate_value(name, field, raw, user, entry, previous):
    kind = field["type"]
    label = f"Field '{name}'"

    # Keeping a value that was already stored is always allowed, so a
    # field set by someone else is not lost when this user saves.
    if previous is not None and raw == previous.get("value") and previous.get("type") == kind:
        return raw

    if kind in REFERENCE_TYPES:
        return _validate_reference(kind, raw, user, entry)

    if kind == "select" and field.get("allow_multi_values"):
        values = _string_list(raw if isinstance(raw, list) else ([raw] if raw else []), label)
        for value in values:
            if value not in field["options"]:
                raise ValidationError(f"{label}: '{value}' is not one of its options.")
        return values

    value = _text(raw, MAX_TEXT, label)
    if not value:
        return ""

    if kind in CHOICE_TYPES:
        if value not in field["options"]:
            raise ValidationError(f"{label}: '{value}' is not one of its options.")
    elif kind == "checkbox":
        if value not in {"on", "true", "1"}:
            raise ValidationError(f"{label}: invalid checkbox value.")
        value = "on"
    elif kind == "number":
        try:
            float(value.replace(",", "."))
        except ValueError:
            raise ValidationError(f"{label}: must be a number.")
        value = value.replace(",", ".")
    elif kind == "date":
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"{label}: must be a date (YYYY-MM-DD).")
    elif kind == "datetime-local":
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"{label}: must be a date and time.")
    elif kind == "time":
        try:
            time.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"{label}: must be a time (HH:MM).")
    elif kind == "email":
        validate_email(value)
    elif kind == "url":
        _url_validator(value)

    return value


def normalize_metadata(raw, *, user, entry):
    """Validate custom fields sent by the editor and return new metadata.

    Unknown top-level keys of the stored metadata are preserved.
    """
    if not isinstance(raw, dict):
        raise ValidationError("Metadata must be an object.")

    previous_meta = entry.metadata if isinstance(entry.metadata, dict) else {}
    previous_fields = previous_meta.get("extra_fields") or {}

    raw_groups = ((raw.get("elabftw") or {}).get("extra_fields_groups")) or []
    if not isinstance(raw_groups, list) or len(raw_groups) > MAX_GROUPS:
        raise ValidationError(f"At most {MAX_GROUPS} field groups.")

    groups = []
    group_ids = set()
    for group in raw_groups:
        if not isinstance(group, dict):
            raise ValidationError("Invalid field group.")
        try:
            group_id = int(group.get("id"))
        except (TypeError, ValueError):
            raise ValidationError("Field group id must be a number.")
        group_name = _text(group.get("name"), 100, "Group name")
        if not group_name or group_id in group_ids:
            raise ValidationError("Field groups need a unique id and a name.")
        group_ids.add(group_id)
        groups.append({"id": group_id, "name": group_name})

    raw_fields = raw.get("extra_fields") or {}
    if not isinstance(raw_fields, dict) or len(raw_fields) > MAX_FIELDS:
        raise ValidationError(f"At most {MAX_FIELDS} custom fields.")

    fields = {}
    for position, (name, field) in enumerate(raw_fields.items()):
        name = _text(name, 100, "Field name")
        if not name:
            raise ValidationError("Every custom field needs a name.")
        if not isinstance(field, dict):
            raise ValidationError(f"Field '{name}': invalid definition.")

        kind = field.get("type")
        if kind not in FIELD_TYPES:
            raise ValidationError(f"Field '{name}': unknown type '{kind}'.")

        clean = {"type": kind}

        if kind in CHOICE_TYPES:
            clean["options"] = _string_list(field.get("options"), f"Field '{name}' options")
            if not clean["options"]:
                raise ValidationError(f"Field '{name}': add at least one option.")
            if kind == "select":
                clean["allow_multi_values"] = bool(field.get("allow_multi_values"))

        if kind == "number":
            clean["units"] = _string_list(field.get("units"), f"Field '{name}' units", 20)
            unit = _text(field.get("unit"), 20, f"Field '{name}' unit")
            if unit and clean["units"] and unit not in clean["units"]:
                raise ValidationError(f"Field '{name}': unit must be one of its units.")
            clean["unit"] = unit or (clean["units"][0] if clean["units"] else "")

        clean["required"] = bool(field.get("required"))
        description = _text(field.get("description"), 500, f"Field '{name}' description")
        if description:
            clean["description"] = description

        group_id = field.get("group_id")
        if group_id not in (None, ""):
            try:
                group_id = int(group_id)
            except (TypeError, ValueError):
                raise ValidationError(f"Field '{name}': invalid group.")
            if group_id not in group_ids:
                raise ValidationError(f"Field '{name}': unknown group.")
            clean["group_id"] = group_id

        clean["position"] = position
        clean["value"] = _validate_value(
            name, clean, field.get("value", ""), user, entry, previous_fields.get(name)
        )
        fields[name] = clean

    metadata = dict(previous_meta)
    metadata["extra_fields"] = fields
    elab = dict(previous_meta.get("elabftw") or {})
    elab["extra_fields_groups"] = groups
    metadata["elabftw"] = elab
    return metadata


def missing_required_fields(metadata):
    fields = (metadata or {}).get("extra_fields") or {}
    return [
        name
        for name, field in fields.items()
        if field.get("required") and field.get("value") in ("", None, [])
    ]


def describe_fields(entry, user):
    """Fields with display labels for reference values, for the page."""
    metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
    fields = metadata.get("extra_fields") or {}
    labels = {}

    for name, field in fields.items():
        kind = field.get("type")
        value = field.get("value")
        if kind in REFERENCE_TYPES and value not in ("", None):
            try:
                obj = reference_queryset(kind, user, entry).filter(pk=int(value)).first()
            except (TypeError, ValueError):
                obj = None
            labels[name] = reference_label(kind, obj) if obj else f"#{value} (not visible)"

    return {
        "metadata": {
            "extra_fields": fields,
            "elabftw": {
                "extra_fields_groups": (metadata.get("elabftw") or {}).get(
                    "extra_fields_groups", []
                )
            },
        },
        "labels": labels,
        "types": FIELD_TYPES,
    }


# --- tags, custom id, rating -------------------------------------------------


def update_header(entry, *, custom_id=None, rating=None, tags=None):
    if custom_id is not None:
        custom_id = _text(custom_id, 64, "Custom ID")
        if not CUSTOM_ID_RE.match(custom_id):
            raise ValidationError("Custom ID: letters, numbers and . : / # - only.")
        entry.custom_id = custom_id

    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise ValidationError("Rating must be 0 to 5.")
        if not 0 <= rating <= 5:
            raise ValidationError("Rating must be 0 to 5.")
        entry.rating = rating

    with transaction.atomic():
        entry.save(update_fields=["custom_id", "rating", "updated_at"])

        if tags is not None:
            names = _string_list(tags, "Tags", MAX_TAGS)
            for name in names:
                if not TAG_RE.match(name):
                    raise ValidationError(f"Tag '{name}': use letters, numbers and . + # / : - only.")
            tag_objects = [
                NotebookTag.objects.get_or_create(name=name.lower())[0]
                for name in names
            ]
            entry.tags.set(tag_objects)

    return entry


# --- steps --------------------------------------------------------------------


def _parse_deadline(value):
    if value in ("", None):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        raise ValidationError("Deadline must be a date and time.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def add_step(entry, body, deadline=None):
    body = _text(body, 500, "Step")
    if not body:
        raise ValidationError("A step needs a description.")
    if entry.steps.count() >= MAX_STEPS:
        raise ValidationError(f"At most {MAX_STEPS} steps.")
    last = entry.steps.order_by("-position").first()
    return NotebookStep.objects.create(
        entry=entry,
        body=body,
        position=(last.position + 1) if last else 0,
        deadline=_parse_deadline(deadline),
    )


def update_step(step, user, *, body=None, finished=None, deadline=None, clear_deadline=False):
    if body is not None:
        body = _text(body, 500, "Step")
        if not body:
            raise ValidationError("A step needs a description.")
        step.body = body
    if finished is not None:
        finished = bool(finished)
        if finished and not step.finished:
            step.finished_at = timezone.now()
            step.finished_by = user
        elif not finished:
            step.finished_at = None
            step.finished_by = None
        step.finished = finished
    if clear_deadline:
        step.deadline = None
    elif deadline is not None:
        step.deadline = _parse_deadline(deadline)
    step.save()
    return step


def reorder_steps(entry, ordered_ids):
    steps = {step.pk: step for step in entry.steps.all()}
    try:
        ordered_ids = [int(pk) for pk in ordered_ids]
    except (TypeError, ValueError):
        raise ValidationError("Invalid step order.")
    if sorted(ordered_ids) != sorted(steps):
        raise ValidationError("Step order must list every step once.")
    with transaction.atomic():
        for position, pk in enumerate(ordered_ids):
            if steps[pk].position != position:
                steps[pk].position = position
                steps[pk].save(update_fields=["position"])


# --- entry links --------------------------------------------------------------


def add_entry_link(entry, target_id, user):
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        raise ValidationError("Invalid entry.")
    if target_id == entry.pk:
        raise ValidationError("An entry cannot link to itself.")
    target = _visible_entries(user).filter(pk=target_id).first()
    if target is None:
        raise ValidationError("Entry does not exist or is not visible to you.")
    if entry.entry_links.count() >= MAX_LINKS:
        raise ValidationError(f"At most {MAX_LINKS} linked entries.")
    link, _created = NotebookEntryLink.objects.get_or_create(
        entry=entry,
        target=target,
        defaults={"created_by": user},
    )
    return link


def serialize_steps(entry):
    return [
        {
            "id": step.pk,
            "body": step.body,
            "finished": step.finished,
            "finished_at": timezone.localtime(step.finished_at).strftime("%Y-%m-%d %H:%M") if step.finished_at else None,
            "finished_by": step.finished_by.get_username() if step.finished_by else None,
            "deadline": timezone.localtime(step.deadline).strftime("%Y-%m-%dT%H:%M") if step.deadline else None,
        }
        for step in entry.steps.select_related("finished_by")
    ]


def serialize_links(entry, user):
    visible = _visible_entries(user)
    outgoing = visible.filter(linked_from__entry=entry)
    incoming = visible.filter(entry_links__target=entry)
    return {
        "outgoing": [
            {"id": e.pk, "label": reference_label("experiments", e), "status": e.status}
            for e in outgoing.distinct()
        ],
        "incoming": [
            {"id": e.pk, "label": reference_label("experiments", e), "status": e.status}
            for e in incoming.distinct()
        ],
    }


def field_definitions_from(source):
    """Field structure of another entry, with values cleared ("Load fields")."""
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    fields = {}
    for name, field in (metadata.get("extra_fields") or {}).items():
        copy = {k: v for k, v in field.items() if k != "value"}
        copy["value"] = [] if field.get("allow_multi_values") else ""
        fields[name] = copy
    return {
        "extra_fields": fields,
        "elabftw": {
            "extra_fields_groups": (metadata.get("elabftw") or {}).get("extra_fields_groups", [])
        },
    }


# --- starting structure for the built-in entry templates ----------------------

def _fields(*specs):
    """specs: (name, type, group_id, extra-dict) tuples."""
    fields = {}
    for position, (name, kind, group_id, extra) in enumerate(specs):
        field = {"type": kind, "value": [] if extra.get("allow_multi_values") else "",
                 "required": False, "position": position}
        if group_id is not None:
            field["group_id"] = group_id
        field.update(extra)
        fields[name] = field
    return fields


TEMPLATE_STRUCTURE = {
    "experiment": {
        "groups": [{"id": 1, "name": "Conditions"}, {"id": 2, "name": "Materials"}],
        "fields": _fields(
            ("Biosafety level", "select", 1, {"options": ["NB-1", "NB-2", "NB-3"], "required": True}),
            ("Temperature", "number", 1, {"units": ["°C"], "unit": "°C"}),
            ("Duration", "number", 1, {"units": ["min", "h", "days"], "unit": "h"}),
            ("Main sample", "items", 2, {}),
            ("Main reagent", "compounds", 2, {}),
        ),
        "steps": ["Prepare materials", "Run the experiment", "Record observations", "Analyse results"],
    },
    "protocol": {
        "groups": [{"id": 1, "name": "Protocol"}],
        "fields": _fields(
            ("Version", "text", 1, {"required": True}),
            ("Biosafety level", "select", 1, {"options": ["NB-1", "NB-2", "NB-3"]}),
            ("Estimated time", "number", 1, {"units": ["min", "h"], "unit": "h"}),
            ("Validated by", "users", 1, {}),
        ),
        "steps": [],
    },
    "analysis": {
        "groups": [{"id": 1, "name": "Analysis"}],
        "fields": _fields(
            ("Source experiment", "experiments", 1, {"required": True}),
            ("Software / pipeline", "text", 1, {}),
            ("Repository or dataset URL", "url", 1, {}),
        ),
        "steps": ["Collect input data", "Run analysis", "Review figures", "Write conclusion"],
    },
    "sample_characterization": {
        "groups": [{"id": 1, "name": "Sample"}, {"id": 2, "name": "Measurements"}],
        "fields": _fields(
            ("Sample", "items", 1, {"required": True}),
            ("Method", "select", 2, {"options": ["Microscopy", "Growth curve", "PCR", "Sequencing", "Mass spectrometry", "Other"], "allow_multi_values": True}),
            ("Measurement date", "date", 2, {}),
        ),
        "steps": ["Retrieve sample", "Prepare aliquot", "Measure", "Store sample back"],
    },
    "plasmid_construction": {
        "groups": [{"id": 1, "name": "Construct"}],
        "fields": _fields(
            ("Backbone", "text", 1, {"required": True}),
            ("Insert", "text", 1, {}),
            ("Cloning method", "select", 1, {"options": ["Restriction/ligation", "Gibson", "Golden Gate", "Gateway", "TOPO", "Other"]}),
            ("Antibiotic resistance", "select", 1, {"options": ["Ampicillin", "Kanamycin", "Chloramphenicol", "Spectinomycin", "Tetracycline", "Other"], "allow_multi_values": True}),
            ("Sequence verified", "checkbox", 1, {}),
        ),
        "steps": ["Design primers", "PCR amplify insert", "Assemble", "Transform", "Screen colonies", "Sequence verify"],
    },
}


def apply_template_structure(entry, template_key):
    """Give a new entry the fields and steps of a built-in template."""
    structure = TEMPLATE_STRUCTURE.get(template_key)
    if not structure:
        return entry
    entry.metadata = {
        "extra_fields": structure["fields"],
        "elabftw": {"extra_fields_groups": structure["groups"]},
    }
    entry.save(update_fields=["metadata"])
    NotebookStep.objects.bulk_create(
        NotebookStep(entry=entry, body=body, position=i)
        for i, body in enumerate(structure["steps"])
    )
    return entry
