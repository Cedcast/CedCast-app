from django import template
import locale

register = template.Library()

@register.filter
def format_number(value):
    """
    Format a number with commas as thousands separators.
    Similar to Django's intcomma filter but doesn't require humanize.
    """
    if value is None:
        return "0"

    try:
        # Convert to int/float if it's a string
        if isinstance(value, str):
            value = float(value) if '.' in value else int(value)

        # Format with commas
        return f"{value:,}"
    except (ValueError, TypeError):
        return str(value)