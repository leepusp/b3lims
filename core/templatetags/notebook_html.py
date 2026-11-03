from django import template
from django.utils.safestring import mark_safe

from core.services.notebook_html import sanitize_notebook_html


register = template.Library()


@register.filter(name="notebook_html")
def notebook_html(value):
    """Render Notebook editor HTML after sanitizing it."""
    return mark_safe(sanitize_notebook_html(value))
