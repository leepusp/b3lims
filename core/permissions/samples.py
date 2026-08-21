# core/permissions/samples.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def _has_group_access(user, obj):
    """Return whether the user is a member or coordinator of the associated research group."""
    if hasattr(obj, 'research_group') and obj.research_group:
        group = obj.research_group
        if group.coordinator == user or group.members.filter(id=user.id).exists():
            return True
    return False

def can_view_sample(user, sample):
    # 1. Generic access: owner, superuser or public object
    if can_view_object(user, sample):
        return True
    # 2. Direct access through the Sample research group
    if _has_group_access(user, sample):
        return True
    # 3. Access inherited through a Collection research group
    for collection in sample.collections.all():
        if _has_group_access(user, collection):
            return True
    return False

def can_edit_sample(user, sample):
    # 1. Generic edit access: owner or superuser
    if can_edit_object(user, sample):
        return True
    # 2. Direct access through the Sample research group
    if _has_group_access(user, sample):
        return True
    # 3. Access inherited through a Collection research group
    for collection in sample.collections.all():
        if _has_group_access(user, collection):
            return True
    return False

def can_delete_sample(user, sample):
    if can_delete_object(user, sample):
        return True

    # Research-group coordinators may delete; ordinary members may not.
    if sample.research_group and sample.research_group.coordinator == user:
        return True

    # Collection research-group coordinators may also delete.
    for collection in sample.collections.all():
        if collection.research_group and collection.research_group.coordinator == user:
            return True

    return False


def visible_samples_for_user(user):
    """
    Return the active samples visible to a user.

    Visibility is intentionally centralized here so list pages, modal selectors,
    network views, and future dashboards do not expose samples outside the user's
    permissions.
    """
    from core.models.samples.sample import Sample

    qs = Sample.objects.filter(is_active=True).select_related(
        "biobank",
        "owner",
        "research_group",
    )

    if getattr(user, "is_superuser", False):
        return qs

    visible_ids = [
        sample.pk
        for sample in qs
        if can_view_sample(user, sample)
    ]

    return Sample.objects.filter(pk__in=visible_ids, is_active=True)
