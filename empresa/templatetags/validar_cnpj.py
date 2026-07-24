# empresa/templatetags/validar_cnpj.py
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_RE_CNPJ_NO_TEXTO = re.compile(
    r"\d{2}\.\d{3}\.\d{3}(?:/\d{4}-\d{2}|\s+\d{4}-\d{2})"
)


@register.filter
def formatar_cnpj(cnpj):
    cnpj = "".join(filter(str.isdigit, str(cnpj)))
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return cnpj


@register.filter
def formatar_cnpj_cpf(doc):
    """Formata CPF (11) ou CNPJ (14); outros tamanhos retorna só dígitos."""
    d = "".join(filter(str.isdigit, str(doc)))
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d or doc or ""


@register.filter
def formatar_cep(cep):
    d = "".join(filter(str.isdigit, str(cep)))
    if len(d) == 8:
        return f"{d[:5]}-{d[5:]}"
    return d or cep or ""


@register.filter
def formatar_telefone_tela(num):
    d = "".join(filter(str.isdigit, str(num)))
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return d or num or ""


@register.filter
def historico_com_links_cnpj(value):
    """
    Destaca trechos no formato de CNPJ (ex.: descrições PIX no extrato) como links.
    """
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""

    def _digitos(t):
        return re.sub(r"\D", "", t or "")

    out = []
    last = 0
    for m in _RE_CNPJ_NO_TEXTO.finditer(s):
        out.append(escape(s[last : m.start()]))
        bruto = m.group(0)
        digitos = _digitos(bruto)
        if len(digitos) == 14:
            out.append(
                '<a href="#" class="extrato-cnpj-link text-primary" '
                'style="text-decoration: underline; cursor: pointer;" '
                'data-cnpj-digits="{}" title="Consultar dados do CNPJ">{}</a>'.format(
                    escape(digitos),
                    escape(bruto),
                )
            )
        else:
            out.append(escape(bruto))
        last = m.end()
    out.append(escape(s[last:]))
    return mark_safe("".join(out))
