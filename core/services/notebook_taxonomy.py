"""Status and category lists for Notebook entries (lab default or per research group)."""

import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.text import slugify

from core.models import NotebookCategory, NotebookEntry, NotebookStatus, ResearchGroup

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FALLBACK_STATUS = "draft"
PROTECTED_SLUGS = {"draft", "archived"}  # used by the Archive action and as the fallback


def can_manage_taxonomy(user, group=None):
    """Superusers manage every list; a group's coordinator manages that group's lists."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return group is not None and group.coordinator_id == user.pk


def can_use_group(user, group):
    """An entry can be filed under a group the user belongs to or coordinates (any, for superusers)."""
    if user.is_superuser:
        return True
    return group.coordinator_id == user.pk or group.members.filter(pk=user.pk).exists()


def user_groups(user):
    if user.is_superuser:
        return ResearchGroup.objects.order_by("name")
    return (
        ResearchGroup.objects.filter(members=user) | ResearchGroup.objects.filter(coordinator=user)
    ).distinct().order_by("name")


def scope_filter(group):
    return {"research_group": group} if group is not None else {"research_group__isnull": True}


def statuses_for(group=None):
    """Statuses an entry of ``group`` may use: the group's own list, else the lab list."""
    if group is not None:
        own = NotebookStatus.objects.filter(research_group=group)
        if own.exists():
            return own
    return NotebookStatus.objects.filter(research_group__isnull=True)


def categories_for(group=None):
    if group is not None:
        own = NotebookCategory.objects.filter(research_group=group)
        if own.exists():
            return own
    return NotebookCategory.objects.filter(research_group__isnull=True)


def status_lookup():
    """slug -> status for every list, used to colour badges on mixed lists."""
    return {s.slug: s for s in NotebookStatus.objects.all()}


def _clean_color(value):
    value = (value or "").strip()
    if not HEX.match(value):
        raise ValidationError("Colour must look like #1a2b3c.")
    return value.lower()


def _clean_name(value):
    value = " ".join((value or "").split())
    if not value:
        raise ValidationError("A name is required.")
    if len(value) > 64:
        raise ValidationError("The name is limited to 64 characters.")
    return value


def _require(user, group):
    if not can_manage_taxonomy(user, group):
        raise PermissionDenied("You cannot edit these lists.")


def _unique_slug(name, group):
    base = slugify(name)[:24] or "status"
    prefix = f"g{group.pk}-" if group is not None else ""
    slug, n = f"{prefix}{base}", 2
    while NotebookStatus.objects.filter(slug=slug).exists():
        slug = f"{prefix}{base}-{n}"
        n += 1
    return slug


def _next_position(model, group):
    last = model.objects.filter(**scope_filter(group)).order_by("-position").first()
    return (last.position + 1) if last else 0


def _name_taken(model, group, name, exclude=None):
    qs = model.objects.filter(**scope_filter(group), name__iexact=name)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.exists()


@transaction.atomic
def create_status(*, user, group, name, color, kind):
    _require(user, group)
    name, color = _clean_name(name), _clean_color(color)
    if kind not in NotebookStatus.Kind.values:
        raise ValidationError("Unknown status type.")
    if _name_taken(NotebookStatus, group, name):
        raise ValidationError("A status with this name already exists in this list.")
    return NotebookStatus.objects.create(
        slug=_unique_slug(name, group),
        name=name,
        color=color,
        kind=kind,
        research_group=group,
        position=_next_position(NotebookStatus, group),
    )


@transaction.atomic
def update_status(*, user, status, name=None, color=None, kind=None):
    _require(user, status.research_group)
    if name is not None:
        name = _clean_name(name)
        if _name_taken(NotebookStatus, status.research_group, name, exclude=status):
            raise ValidationError("A status with this name already exists in this list.")
        status.name = name
    if color is not None:
        status.color = _clean_color(color)
    if kind is not None:
        if kind not in NotebookStatus.Kind.values:
            raise ValidationError("Unknown status type.")
        status.kind = kind
    status.save()
    return status


@transaction.atomic
def delete_status(*, user, status):
    """Delete a status; entries that used it fall back to the first status of the lab list."""
    _require(user, status.research_group)
    # A group with no statuses of its own simply uses the lab list again; the lab list cannot be empty.
    siblings = NotebookStatus.objects.filter(**scope_filter(status.research_group)).exclude(pk=status.pk)
    if status.research_group_id is None and not siblings.exists():
        raise ValidationError("The lab list needs at least one status.")
    if status.slug in PROTECTED_SLUGS:
        raise ValidationError("Draft and Archived are built in and cannot be removed.")
    moved = NotebookEntry.objects.filter(status=status.slug).update(status=FALLBACK_STATUS)
    status.delete()
    return moved


@transaction.atomic
def reorder(*, user, model, group, ids):
    _require(user, group)
    rows = {r.pk: r for r in model.objects.filter(**scope_filter(group))}
    if set(ids) != set(rows):
        raise ValidationError("The order must list every item of this list exactly once.")
    for position, pk in enumerate(ids):
        if rows[pk].position != position:
            rows[pk].position = position
            rows[pk].save(update_fields=["position"])


@transaction.atomic
def create_category(*, user, group, name, color):
    _require(user, group)
    name, color = _clean_name(name), _clean_color(color)
    if _name_taken(NotebookCategory, group, name):
        raise ValidationError("A category with this name already exists in this list.")
    return NotebookCategory.objects.create(
        name=name, color=color, research_group=group, position=_next_position(NotebookCategory, group)
    )


@transaction.atomic
def update_category(*, user, category, name=None, color=None):
    _require(user, category.research_group)
    if name is not None:
        name = _clean_name(name)
        if _name_taken(NotebookCategory, category.research_group, name, exclude=category):
            raise ValidationError("A category with this name already exists in this list.")
        category.name = name
    if color is not None:
        category.color = _clean_color(color)
    category.save()
    return category


@transaction.atomic
def delete_category(*, user, category):
    _require(user, category.research_group)
    moved = NotebookEntry.objects.filter(category=category).count()
    category.delete()  # entries keep existing; their category is cleared (SET_NULL)
    return moved


def editable_groups(user):
    """Groups whose lists this user may edit (None stands for the lab-wide list)."""
    if user.is_superuser:
        return list(ResearchGroup.objects.order_by("name"))
    return list(user.coordinated_research_groups.order_by("name"))


def resolve_status_slug(entry, slug):
    """True when ``slug`` is allowed for this entry's list."""
    return statuses_for(entry.research_group).filter(slug=slug).exists()
