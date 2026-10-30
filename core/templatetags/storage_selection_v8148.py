"""Permission-aware inventory selection for physical storage."""
from django import template
from core.permissions.storage_workspaces_v8 import can_operate_on_sample_storage

register = template.Library()

@register.filter
def can_select_for_storage(sample, user):
    if not hasattr(sample, "_storage_selection_v8148"):
        sample._storage_selection_v8148 = bool(
            can_operate_on_sample_storage(user, sample)
        )
    return sample._storage_selection_v8148
