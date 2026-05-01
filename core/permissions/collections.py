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
