from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return ""

    try:
        return dictionary.get(key, "")
    except Exception:
        return ""


@register.filter
def split(value, separator=","):
    if value is None:
        return []

    return str(value).split(separator)


@register.filter
def type_fields(sample):
    """(label, value) pairs of the extra fields of a Sample whose type an installation defined."""
    from core.services import sample_types

    return sample_types.describe(sample)
