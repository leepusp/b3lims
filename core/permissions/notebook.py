from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, Exists, OuterRef, Q
from django.db.models.functions import Cast
from django.utils import timezone

from core.models.access_grants import ResourceAccessGrant
from core.models.lab_tools.notebook import NotebookEntry

LEVEL_RANK = {"view": 1, "edit": 2, "manage": 3}

# Explicit grants only take effect while the entry is shared with someone.
# A private entry stays private to its author even if grants were left behind.
GRANT_VISIBILITIES = ("shared", "lab")


def _entry_content_type():
    return ContentType.objects.get_for_model(NotebookEntry, for_concrete_model=False)


def _user_grants_subquery(user, levels):
    now = timezone.now()
    return (
        ResourceAccessGrant.objects.filter(
            content_type=_entry_content_type(),
            object_id=Cast(OuterRef("pk"), CharField()),
            revoked_at__isnull=True,
            access_level__in=levels,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .filter(
            Q(user=user)
            | Q(research_group__coordinator=user)
            | Q(research_group__members=user)
        )
    )


def visible_notebook_entries_for_user(user):
    """
    Return notebook entries visible to the given user.

    - superuser: all entries
    - private: only the author
    - lab: any authenticated user
    - shared: the author, plus users and research groups holding an active grant
    - a grant also counts on "lab" entries (it adds edit rights there)
    Entries in the trash are never listed here; see trashed_notebook_entries_for_user.
    """
    qs = NotebookEntry.objects.filter(deleted_at__isnull=True)

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    granted = Exists(_user_grants_subquery(user, LEVEL_RANK))
    return qs.filter(
        Q(author=user)
        | Q(visibility="lab")
        | (Q(visibility="shared") & granted)
    ).distinct()


def trashed_notebook_entries_for_user(user):
    """Entries in the trash that this user may restore or delete for good:
    their own, or any for a superuser."""
    qs = NotebookEntry.objects.filter(deleted_at__isnull=False)

    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs
    return qs.filter(author=user)


def shared_with_user(user):
    """Entries other people shared with this user through an explicit grant."""
    base = visible_notebook_entries_for_user(user).exclude(author=user)
    if not user or not user.is_authenticated:
        return base.none()
    return base.filter(Exists(_user_grants_subquery(user, LEVEL_RANK)))


def grant_level(user, entry):
    """Highest active explicit level this user holds on the entry, or None.

    Grants only count while the entry is shared or lab-wide.
    """
    if not user or not user.is_authenticated or entry is None or entry.pk is None:
        return None
    if entry.visibility not in GRANT_VISIBILITIES:
        return None
    now = timezone.now()
    levels = (
        ResourceAccessGrant.objects.filter(
            content_type=_entry_content_type(),
            object_id=str(entry.pk),
            revoked_at__isnull=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .filter(
            Q(user=user)
            | Q(research_group__coordinator=user)
            | Q(research_group__members=user)
        )
        .values_list("access_level", flat=True)
    )
    best = None
    for level in levels:
        if best is None or LEVEL_RANK[level] > LEVEL_RANK[best]:
            best = level
    return best


def _at_least(user, entry, level):
    held = grant_level(user, entry)
    return held is not None and LEVEL_RANK[held] >= LEVEL_RANK[level]


def can_view_notebook_entry(user, entry) -> bool:
    if not user or not user.is_authenticated or entry is None:
        return False

    if entry.deleted_at is not None:
        return False

    if user.is_superuser:
        return True

    if entry.author_id == user.id:
        return True

    if entry.visibility == "lab":
        return True

    return _at_least(user, entry, "view")


def can_edit_notebook_entry(user, entry) -> bool:
    """Change the content of an entry: author, superuser, or an edit/manage grant."""
    if not user or not user.is_authenticated or entry is None:
        return False

    if user.is_superuser:
        return True

    if entry.author_id == user.id:
        return True

    return entry.deleted_at is None and _at_least(user, entry, "edit")


def can_manage_notebook_entry_sharing(user, entry) -> bool:
    """Change who an entry is shared with: author, superuser, or a manage grant."""
    if not user or not user.is_authenticated or entry is None:
        return False

    if user.is_superuser or entry.author_id == user.id:
        return True

    return entry.deleted_at is None and _at_least(user, entry, "manage")


def can_delete_notebook_entry(user, entry) -> bool:
    """Trash, restore or purge an entry: only its author or a superuser.

    Sharing never hands out the right to destroy somebody else's record.
    """
    if not user or not user.is_authenticated or entry is None:
        return False
    return bool(user.is_superuser or entry.author_id == user.id)
