from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key"""
    try:
        return dictionary.get(key, 0)
    except (AttributeError, TypeError):
        return 0

@register.filter
def add(value, arg):
    """Add two values"""
    try:
        return value + arg
    except (TypeError, ValueError):
        return value

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return value - arg
    except (TypeError, ValueError):
        return value

@register.filter
def multiply(value, arg):
    """Multiply value by arg"""
    try:
        return value * arg
    except (TypeError, ValueError):
        return value

@register.filter
def divide(value, arg):
    """Divide value by arg"""
    try:
        if arg and arg != 0:
            return value / arg
        return 0
    except (TypeError, ValueError):
        return 0