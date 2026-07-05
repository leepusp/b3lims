# core/permissions/collections.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def _has_group_access(user, collection):
    if collection.research_group:
        group = collection.research_group
        if group.coordinator == user or group.members.filter(id=user.id).exists():
            return True
    return False

def can_view_collection(user, collection):
    if can_view_object(user, collection):
        return True
    return _has_group_access(user, collection)

def can_edit_collection(user, collection):
    if can_edit_object(user, collection):
        return True
    return _has_group_access(user, collection)

def can_delete_collection(user, collection):
    if can_delete_object(user, collection):
        return True
    # Apenas o Coordenador do grupo pode deletar a coleção inteira
    if collection.research_group and collection.research_group.coordinator == user:
        return True
    return False

def can_manage_collection_permissions(user, collection):
    return can_edit_collection(user, collection)


def visible_collections_for_user(user):
    """
    Return active collections visible to a user.

    Visibility is centralized here so list pages, selectors, and future
    dashboards do not expose collections outside the user's permissions.
    """
    from core.models import Collection

    qs = Collection.objects.filter(is_active=True).select_related(
        "owner",
        "research_group",
    )

    if getattr(user, "is_superuser", False):
        return qs

    visible_ids = [
        collection.pk
        for collection in qs
        if can_view_collection(user, collection)
    ]

    return Collection.objects.filter(pk__in=visible_ids, is_active=True)
