"""Template tags for experimental ELN navigation."""

from django import template

from core.permissions.eln_experimental import (
    can_access_eln_experimental,
)

register = template.Library()


@register.simple_tag
def eln_experimental_allowed(user):
    return can_access_eln_experimental(user)
