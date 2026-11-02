"""Who may book and manage Lab Calendar equipment.

Built on core's research groups and ResourceAccessGrant:
- book: superuser, coordinator or member of the resource's research group,
  or an explicit grant of level "edit" or higher;
- manage: superuser, coordinator of the resource's research group, or an
  explicit grant of level "manage".
"""

from core.models import ResourceAccessGrant
from core.services.resource_access import has_explicit_resource_access


def _is_authenticated(user):
    return bool(user and user.is_authenticated)


def _in_group(user, group):
    if group is None:
        return False
    if group.coordinator_id == user.pk:
        return True
    return group.members.filter(pk=user.pk).exists()


def can_manage_resource(user, resource) -> bool:
    if not _is_authenticated(user) or resource is None:
        return False
    if user.is_superuser:
        return True
    group = resource.research_group
    if group is not None and group.coordinator_id == user.pk:
        return True
    return has_explicit_resource_access(user, resource, ResourceAccessGrant.AccessLevel.MANAGE)


def can_book_resource(user, resource) -> bool:
    if not _is_authenticated(user) or resource is None:
        return False
    if not (resource.is_active and resource.is_bookable):
        return False
    if user.is_superuser:
        return True
    if _in_group(user, resource.research_group):
        return True
    return has_explicit_resource_access(user, resource, ResourceAccessGrant.AccessLevel.EDIT)


def can_manage_booking(user, booking) -> bool:
    if not _is_authenticated(user) or booking is None:
        return False
    if booking.user_id == user.pk:
        return True
    return can_manage_resource(user, booking.resource)
