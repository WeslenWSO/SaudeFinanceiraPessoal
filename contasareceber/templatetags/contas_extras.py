from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter(name='moeda_br')
def moeda_br(value):
    """Formata número no padrão brasileiro com milhar: 1.100,00"""
    if value is None or value == '':
        return '0,00'
    try:
        return number_format(value, decimal_pos=2, force_grouping=True, use_l10n=True)
    except (TypeError, ValueError):
        return str(value)
