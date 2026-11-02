from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from core.services.extension_panels import panels_for


register = template.Library()


@register.simple_tag(takes_context=True)
def extension_panels(context, slot, obj=None):
    """Render every panel registered for ``slot``.

    Usage::

        {% load extension_panels %}
        {% extension_panels "notebook_entry.sidebar" entry %}
    """
    request = context.get("request")
    html = []
    for panel in panels_for(slot, request, obj):
        panel_context = {
            "request": request,
            "user": getattr(request, "user", None),
            "panel_title": panel["title"],
            "object": obj,
            **panel["context"],
        }
        html.append(render_to_string(panel["template"], panel_context, request=request))
    return mark_safe("".join(html))
