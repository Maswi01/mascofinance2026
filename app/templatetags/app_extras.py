# app/templatetags/app_extras.py
from django import template
register = template.Library()

@register.filter
def list_index(lst, i):
    try:
        return lst[i]
    except (IndexError, TypeError):
        return {}