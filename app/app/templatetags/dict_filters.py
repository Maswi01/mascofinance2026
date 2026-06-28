# templatetags/dict_filters.py
# Place this file in your app's templatetags/ folder.
# Make sure templatetags/__init__.py exists too.
#
# Usage in template:  {{ my_dict|get_item:key }}

from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Return dictionary[key], or None if missing."""
    if dictionary is None:
        return None
    return dictionary.get(key)