# core/permissions/biobanks.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def can_view_biobank(user, biobank):
    return can_view_object(user, biobank)

def can_edit_biobank(user, biobank):
    return can_edit_object(user, biobank)

def can_delete_biobank(user, biobank):
    return can_delete_object(user, biobank)

def can_manage_biobank_permissions(user, biobank):
    # Simplificado: quem tem poder para editar, tem poder para gerenciar o biobanco
    return can_edit_object(user, biobank)
