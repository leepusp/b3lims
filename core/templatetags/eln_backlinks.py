from django import template

from core.services.notebook_backlinks import RESOLVERS

register = template.Library()


@register.inclusion_tag("internal/lab_tools/_eln_backlinks.html", takes_context=True)
def eln_backlinks(context, kind, obj):
    """Render the "Used in experiments" panel for a LIMS entity."""
    request = context.get("request")
    user = getattr(request, "user", None)
    items = []
    if obj is not None and user is not None and kind in RESOLVERS:
        items = RESOLVERS[kind](user, obj)
    return {"items": items}
