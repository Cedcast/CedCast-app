from django import template
import locale

register = template.Library()

@register.filter
def split(value, arg):
    """
    Split a string by a delimiter and return the list.
    Usage: {{ value|split:" " }}
    """
    if not value:
        return []
    return str(value).split(str(arg))


@register.filter
def first(value):
    """
    Get the first item from a list.
    Usage: {{ list|first }}
    """
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return value


@register.filter
def slice_filter(value, arg):
    """
    Slice a list using Python slice notation.
    Usage: {{ list|slice:"1:" }}
    """
    if isinstance(value, (list, tuple)):
        try:
            start, end = arg.split(':')
            start = int(start) if start else None
            end = int(end) if end else None
            return value[start:end]
        except (ValueError, AttributeError):
            return value
    return value


@register.filter
def join(value, arg):
    """
    Join a list with a separator.
    Usage: {{ list|join:" " }}
    """
    if isinstance(value, (list, tuple)):
        return str(arg).join(str(item) for item in value)
    return value