from __future__ import annotations

from django.db.models import Q

from core.models.lab_tools.notebook import NotebookEntry


def visible_notebook_entries_for_user(user):
    """
    Return notebook entries visible to the given user.

    Current policy without extra sharing tables:
    - superuser: all entries
    - private: only the author
    - lab: any authenticated user
    - shared: only the author for now, until explicit sharing fields are added
    Entries in the trash are never listed here; see trashed_notebook_entries_for_user.
    """
    qs = NotebookEntry.objects.filter(deleted_at__isnull=True)

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    return qs.filter(
        Q(author=user)
        | Q(visibility="lab")
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

    return False


def can_edit_notebook_entry(user, entry) -> bool:
    if not user or not user.is_authenticated or entry is None:
        return False

    if user.is_superuser:
        return True

    return entry.author_id == user.id
