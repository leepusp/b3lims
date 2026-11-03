"""Share Notebook entries with users and research groups.

Built on the project's generic ResourceAccessGrant, the same mechanism that shares
Collections, so grants are auditable, can expire and are revoked, never deleted.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils import timezone

from core.models import ResearchGroup
from core.models.lab_tools.notebook import NotebookEntry
from core.permissions.notebook import can_manage_notebook_entry_sharing
from core.models.lab_tools.notebook_collab import NotebookEditLock
from core.services.resource_access import (
    active_resource_grants,
    grant_resource_access,
    revoke_resource_access,
)

LEVELS = (("view", "Can read"), ("edit", "Can edit"), ("manage", "Can edit and share"))
VISIBILITIES = (
    ("private", "Only me"),
    ("shared", "People I choose"),
    ("lab", "Whole lab (read)"),
)


def _check_entry(entry):
    if not isinstance(entry, NotebookEntry) or entry.pk is None:
        raise ValidationError("Sharing requires a saved Notebook entry.")
    if entry.deleted_at is not None:
        raise ValidationError("An entry in the trash cannot be shared.")


def _require_manager(user, entry):
    if not can_manage_notebook_entry_sharing(user, entry):
        raise PermissionDenied("You do not have permission to manage this entry's sharing.")


def entry_grants(entry):
    _check_entry(entry)
    return (
        active_resource_grants(entry)
        .select_related("user", "research_group")
        .order_by("research_group__name", "user__username", "id")
    )


def grant_payload(grant):
    if grant.user_id:
        user = grant.user
        name = user.get_full_name() or user.get_username()
        kind, ident, detail = "user", user.pk, user.get_username()
    else:
        name = grant.research_group.name
        kind, ident, detail = "group", grant.research_group_id, "Research group"
    return {
        "id": grant.pk,
        "kind": kind,
        "principal_id": ident,
        "name": name,
        "detail": detail,
        "level": grant.access_level,
        "expires_at": timezone.localtime(grant.expires_at).date().isoformat() if grant.expires_at else "",
    }


def share_entry(*, entry, granted_by, level, user=None, research_group=None, expires_at=None):
    """Grant or update access. A private entry becomes "shared" so the grant takes effect."""
    _check_entry(entry)
    _require_manager(granted_by, entry)

    if level not in dict(LEVELS):
        raise ValidationError("Choose a valid access level.")
    if user is not None and not user.is_active:
        raise ValidationError("Access cannot be granted to an inactive user.")
    if user is not None and user.pk == entry.author_id:
        raise ValidationError("The author already has full access.")
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError("The expiration date must be in the future.")

    grant = grant_resource_access(
        resource=entry,
        access_level=level,
        granted_by=granted_by,
        user=user,
        research_group=research_group,
        expires_at=expires_at,
    )
    if entry.visibility == "private":
        entry.visibility = "shared"
        entry.save(update_fields=["visibility"])
    return grant


def unshare_entry(*, entry, grant_id, revoked_by):
    _check_entry(entry)
    _require_manager(revoked_by, entry)
    grant = active_resource_grants(entry).filter(pk=grant_id).first()
    if grant is None:
        raise ValidationError("That access entry no longer exists.")
    return revoke_resource_access(grant=grant, revoked_by=revoked_by)


def set_visibility(*, entry, value, changed_by):
    _check_entry(entry)
    _require_manager(changed_by, entry)
    if value not in dict(VISIBILITIES):
        raise ValidationError("Choose a valid visibility.")
    # Only the author or a superuser may open an entry to the whole lab or close it.
    if value in ("lab", "private") and not (
        changed_by.is_superuser or changed_by.pk == entry.author_id
    ):
        raise PermissionDenied("Only the author can make an entry public to the lab or private.")
    entry.visibility = value
    entry.save(update_fields=["visibility"])
    return entry


def search_principals(*, query, entry, limit=8):
    """Users and research groups matching a typed name, excluding the author."""
    needle = (query or "").strip()
    if len(needle) < 2:
        return []
    User = get_user_model()
    users = (
        User.objects.filter(is_active=True)
        .exclude(pk=entry.author_id)
        .filter(
            Q(username__icontains=needle)
            | Q(first_name__icontains=needle)
            | Q(last_name__icontains=needle)
            | Q(email__icontains=needle)
        )
        .order_by("username")[:limit]
    )
    groups = ResearchGroup.objects.filter(name__icontains=needle).order_by("name")[:limit]
    found = [
        {
            "kind": "group",
            "principal_id": g.pk,
            "name": g.name,
            "detail": "Research group",
        }
        for g in groups
    ]
    found += [
        {
            "kind": "user",
            "principal_id": u.pk,
            "name": u.get_full_name() or u.get_username(),
            "detail": u.get_username(),
        }
        for u in users
    ]
    return found


def transfer_ownership(*, entry, grant_id, by):
    """Make a person who already has access the author; the former author keeps edit access.

    Only the current author or a superuser may do this. The entry keeps its history
    (revisions, comments, files); only ``author`` changes.
    """
    from django.db import transaction

    _check_entry(entry)
    if not (by.is_superuser or by.pk == entry.author_id):
        raise PermissionDenied("Only the author can transfer ownership.")
    grant = active_resource_grants(entry).filter(pk=grant_id, user__isnull=False).select_related("user").first()
    if grant is None:
        raise ValidationError("Choose a person who already has access to this entry.")
    new_author = grant.user
    if not new_author.is_active:
        raise ValidationError("Ownership cannot go to an inactive user.")
    if new_author.pk == entry.author_id:
        raise ValidationError("That person is already the author.")

    with transaction.atomic():
        former = entry.author
        entry.author = new_author
        # The former author must not lose the entry: it becomes shared, with edit access.
        if entry.visibility == "private":
            entry.visibility = "shared"
        entry.save(update_fields=["author", "visibility"])
        revoke_resource_access(grant=grant, revoked_by=by)  # the new author needs no grant
        grant_resource_access(
            resource=entry, access_level="edit", granted_by=by, user=former,
        )
        NotebookEditLock.objects.filter(entry=entry).delete()
    return entry
