from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def sum_attr(queryset, attr):
    """Sum a specific attribute from a list of dictionaries"""
    total = Decimal('0.00')
    for item in queryset:
        try:
            total += item.get(attr, Decimal('0.00'))
        except (TypeError, ValueError):
            pass
    return total

@register.filter
def div(value, arg):
    """Divide value by arg"""
    try:
        return Decimal(str(value)) / Decimal(str(arg))
    except (ValueError, ZeroDivisionError, TypeError, Decimal.DivisionByZero):
        return Decimal('0.00')