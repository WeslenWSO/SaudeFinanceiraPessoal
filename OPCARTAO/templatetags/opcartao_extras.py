from django import template

from OPCARTAO.bandeiras import resolver_bandeira
from OPCARTAO.agrupamento import resumo_cartoes_fatura
from OPCARTAO.categorias import LEGENDA_POR_SLUG, categoria_efetiva

register = template.Library()


@register.inclusion_tag('OPCARTAO/_bandeira_icone.html')
def bandeira_icone(bandeira='', cartao=None):
    codigo = ''
    if cartao is not None:
        codigo = getattr(cartao, 'bandeira', '') or ''
    info = resolver_bandeira(codigo, bandeira)
    return {
        'icone': info['icone'],
        'cor': info['cor'],
        'nome': info['nome'],
    }


@register.filter
def resumo_cartoes(fatura):
    return resumo_cartoes_fatura(fatura)


@register.filter
def categoria_legenda(item):
    if item is None:
        return None
    if hasattr(item, 'descricao'):
        slug = categoria_efetiva(item.descricao, item.categoria, item.tipo_compra)
    else:
        slug = item
    return LEGENDA_POR_SLUG.get(slug or 'outros')


@register.filter
def bandeira_info(valor):
    if hasattr(valor, 'bandeira'):
        cartao = getattr(valor, 'cartao', None)
        return resolver_bandeira(
            getattr(cartao, 'bandeira', '') if cartao else '',
            getattr(valor, 'bandeira', ''),
        )
    return resolver_bandeira(valor)
