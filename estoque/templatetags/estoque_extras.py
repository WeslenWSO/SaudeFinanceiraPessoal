from django import template

from estoque.setores import rotulo_setor as _rotulo_setor

register = template.Library()


@register.filter
def setor_rotulo(codigo):
    return _rotulo_setor(codigo)
