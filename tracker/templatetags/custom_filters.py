from django import template

register = template.Library()

@register.filter
def min_value(value, arg):
    try:
        return min(float(value), float(arg))
    except (ValueError, TypeError):
        return value 

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return '' 