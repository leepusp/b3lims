# core/permissions/collections.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def can_view_collection(user, collection):
    return can_view_object(user, collection)

def can_edit_collection(user, collection):
    return can_edit_object(user, collection)

def can_delete_collection(user, collection):
    return can_delete_object(user, collection)

def can_manage_collection_permissions(user, collection):
    # Simplificado: quem tem poder para editar, tem poder para gerenciar a coleção
    return can_edit_object(user, collection)
