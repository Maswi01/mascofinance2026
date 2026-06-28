# app/templatetags/report_tags.py
# Place this file in your app's templatetags/ folder
# Make sure templatetags/__init__.py exists (can be empty)

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get a value from a dict using a variable key in templates.
    Usage: {{ my_dict|get_item:office.id }}
    """
    if dictionary is None:
        return 0
    val = dictionary.get(key, 0)
    if val is None:
        return 0
    return val


@register.filter
def fmt_num(value):
    """Format a number with commas, show 0 as '0', negatives as-is."""
    try:
        from decimal import Decimal
        v = Decimal(str(value))
        if v == 0:
            return '0'
        # Format with commas, strip trailing zeros after decimal
        formatted = '{:,.2f}'.format(v)
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return formatted
    except Exception:
        return str(value)