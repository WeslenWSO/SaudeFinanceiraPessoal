from django import template
from django.templatetags.static import static
from django.utils.formats import number_format
import re

register = template.Library()

_BANCOS_LOGO_STATIC = {
    '237': 'img/bancos/bradesco.png',
    '104': 'img/bancos/caixa.png',
    '999': 'img/bancos/caixa.png',
    '707': 'img/bancos/daycoval.png',
}


@register.filter(name='moeda_br')
def moeda_br(value):
    """Formata número no padrão brasileiro com milhar: 17.920,00"""
    if value is None or value == '':
        return '0,00'
    try:
        return number_format(value, decimal_pos=2, force_grouping=True, use_l10n=True)
    except (TypeError, ValueError):
        return str(value)


@register.filter(name='mascara_cpf')
def mascara_cpf(valor):
    """Oculta os 6 dígitos centrais do CPF (ex.: 025.***.***-73)."""
    if not valor:
        return ''
    digits = re.sub(r'\D', '', str(valor))
    if len(digits) != 11:
        return str(valor)
    return f'{digits[:3]}.***.***-{digits[-2:]}'


def _codigo_banco(banco):
    if not banco:
        return ''
    return str(banco.codigo or '').strip()


def _eh_bradesco(banco):
    if not banco:
        return False
    cod = _codigo_banco(banco)
    if cod in ('237', '0237'):
        return True
    return 'BRADESCO' in str(banco.nome or '').upper()


def _eh_caixa(banco):
    if not banco:
        return False
    cod = _codigo_banco(banco)
    if cod in ('104', '0104', '999'):
        return True
    nome = str(banco.nome or '').upper()
    return nome == 'CAIXA' or 'CAIXA ECON' in nome


def _eh_daycoval(banco):
    if not banco:
        return False
    cod = _codigo_banco(banco)
    if cod in ('707', '0707'):
        return True
    return 'DAYCOVAL' in str(banco.nome or '').upper()


@register.filter
def banco_logo_url(banco):
    """URL do logo: cadastro (media) ou fallback estático conhecido."""
    if not banco:
        return ''
    if banco.logo:
        return banco.logo.url
    cod = _codigo_banco(banco)
    path = _BANCOS_LOGO_STATIC.get(cod)
    if not path and _eh_bradesco(banco):
        path = _BANCOS_LOGO_STATIC['237']
    if not path and _eh_caixa(banco):
        path = _BANCOS_LOGO_STATIC['104']
    if not path and _eh_daycoval(banco):
        path = _BANCOS_LOGO_STATIC['707']
    if path:
        return static(path)
    return ''
