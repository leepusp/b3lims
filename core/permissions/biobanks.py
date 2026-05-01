# core/permissions/biobanks.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def _has_group_access(user, biobank):
    if biobank.research_group:
        group = biobank.research_group
        if group.coordinator == user or group.members.filter(id=user.id).exists():
            return True
    return False

def can_view_biobank(user, biobank):
    if can_view_object(user, biobank):
        return True
    return _has_group_access(user, biobank)

def can_edit_biobank(user, biobank):
    if can_edit_object(user, biobank):
        return True
    return _has_group_access(user, biobank)

def can_delete_biobank(user, biobank):
    if can_delete_object(user, biobank):
        return True
    if biobank.research_group and biobank.research_group.coordinator == user:
        return True
    return False

def can_manage_biobank_permissions(user, biobank):
    return can_edit_biobank(user, biobank)
