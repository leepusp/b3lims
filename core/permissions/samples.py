# core/permissions/samples.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def can_view_sample(user, sample):
    return can_view_object(user, sample)

def can_edit_sample(user, sample):
    return can_edit_object(user, sample)

def can_delete_sample(user, sample):
    return can_delete_object(user, sample)
