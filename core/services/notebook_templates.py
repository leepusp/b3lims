"""User-made entry templates: save an entry as a template, share it, start entries from it."""

import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from core.models import NotebookEntry, NotebookTemplate, ResearchGroup
from core.models.lab_tools.notebook_composer import NotebookStep
from core.services.notebook_composer import field_definitions_from

ICON_RE = re.compile(r"^bi-[a-z0-9-]{1,36}$")
MAX_STEPS = 50
KEY_PREFIX = "t"


def _group_ids(user):
    return list(
        ResearchGroup.objects.filter(Q(members=user) | Q(coordinator=user)).values_list("pk", flat=True).distinct()
    )


def templates_for(user):
    """Templates this user can start an entry from."""
    qs = NotebookTemplate.objects.select_related("research_group", "owner")
    if user.is_superuser:
        return qs
    return qs.filter(
        Q(owner=user)
        | Q(visibility=NotebookTemplate.Visibility.LAB)
        | Q(visibility=NotebookTemplate.Visibility.GROUP, research_group_id__in=_group_ids(user))
    ).distinct()


def can_use(user, template):
    return templates_for(user).filter(pk=template.pk).exists()


def can_edit(user, template):
    if user.is_superuser or template.owner_id == user.pk:
        return True
    group = template.research_group
    return (
        template.visibility == NotebookTemplate.Visibility.GROUP
        and group is not None
        and group.coordinator_id == user.pk
    )


def _check_sharing(user, visibility, group):
    """Private is open to everyone; a group needs its coordinator; the whole lab needs a superuser."""
    V = NotebookTemplate.Visibility
    if visibility not in V.values:
        raise ValidationError("Unknown visibility.")
    if visibility == V.PRIVATE:
        return None
    if visibility == V.LAB:
        if not user.is_superuser:
            raise PermissionDenied("Only superusers can share a template with the whole lab.")
        return None
    if group is None:
        raise ValidationError("Choose the research group to share with.")
    if not (user.is_superuser or group.coordinator_id == user.pk):
        raise PermissionDenied("Only the group's coordinator can share a template with the group.")
    return group


def _clean_text(value, limit, label, required=False):
    value = " ".join((value or "").split())
    if required and not value:
        raise ValidationError(f"{label} is required.")
    if len(value) > limit:
        raise ValidationError(f"{label} is limited to {limit} characters.")
    return value


def _clean_icon(value):
    value = (value or "").strip() or "bi-file-earmark-text"
    if not ICON_RE.match(value):
        raise ValidationError("Invalid icon.")
    return value


def _structure_of(entry):
    structure = field_definitions_from(entry)
    structure["steps"] = [s.body for s in entry.steps.all()[:MAX_STEPS]]
    return structure


@transaction.atomic
def save_entry_as_template(*, entry, user, name, description="", visibility="private", group=None, template=None, icon=None):
    """Create a template from ``entry``, or overwrite ``template`` with the entry's current content."""
    name = _clean_text(name, 120, "The name", required=True)
    description = _clean_text(description, 300, "The description")
    group = _check_sharing(user, visibility, group)
    entry_type = entry.entry_type if entry.entry_type in dict(NotebookEntry.ENTRY_TYPE_CHOICES) else "other"
    values = {
        "name": name,
        "description": description,
        "title": (entry.title or "Untitled entry")[:255],
        "entry_type": entry_type,
        "content": entry.content or "",
        "protocol_content": entry.protocol_content or "",
        "structure": _structure_of(entry),
        "visibility": visibility,
        "research_group": group,
    }
    if icon is not None:
        values["icon"] = _clean_icon(icon)
    if template is not None:
        if not can_edit(user, template):
            raise PermissionDenied("You cannot change this template.")
        for key, value in values.items():
            setattr(template, key, value)
        template.save()
        return template
    return NotebookTemplate.objects.create(owner=user, **values)


@transaction.atomic
def update_template(*, user, template, name=None, description=None, icon=None, visibility=None, group=None):
    if not can_edit(user, template):
        raise PermissionDenied("You cannot change this template.")
    if name is not None:
        template.name = _clean_text(name, 120, "The name", required=True)
    if description is not None:
        template.description = _clean_text(description, 300, "The description")
    if icon is not None:
        template.icon = _clean_icon(icon)
    if visibility is not None and (visibility != template.visibility or group != template.research_group):
        template.research_group = _check_sharing(user, visibility, group)
        template.visibility = visibility
    template.save()
    return template


def delete_template(*, user, template):
    if not can_edit(user, template):
        raise PermissionDenied("You cannot remove this template.")
    template.delete()


def key_for(template):
    return f"{KEY_PREFIX}{template.pk}"


def template_from_key(key, user):
    """The usable template for a menu key such as ``t12``, or None."""
    if not isinstance(key, str) or not re.fullmatch(rf"{KEY_PREFIX}\d+", key):
        return None
    return templates_for(user).filter(pk=int(key[len(KEY_PREFIX):])).first()


def menu_entries(user):
    """Custom templates in the shape the "New entry" menu already renders."""
    return {
        key_for(t): {
            "label": t.name,
            "description": t.description or "Saved template",
            "icon": t.icon,
            "custom": True,
        }
        for t in templates_for(user)
    }


@transaction.atomic
def create_entry_from_template(*, user, template):
    entry = NotebookEntry.objects.create(
        title=template.title,
        author=user,
        entry_type=template.entry_type if template.entry_type in dict(NotebookEntry.ENTRY_TYPE_CHOICES) else "other",
        status="draft",
        visibility="private",
        content=template.content,
        protocol_content=template.protocol_content,
    )
    structure = template.structure if isinstance(template.structure, dict) else {}
    if structure.get("extra_fields"):
        entry.metadata = {
            "extra_fields": structure["extra_fields"],
            "elabftw": structure.get("elabftw") or {},
        }
        entry.save(update_fields=["metadata"])
    steps = [str(s)[:500] for s in (structure.get("steps") or [])[:MAX_STEPS] if str(s).strip()]
    NotebookStep.objects.bulk_create(NotebookStep(entry=entry, body=body, position=i) for i, body in enumerate(steps))
    return entry
