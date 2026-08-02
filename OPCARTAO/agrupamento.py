"""Agrupamento de lançamentos da fatura por cartão."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from .categorias import categoria_efetiva

_RE_PARCELA = re.compile(r'^(\d{1,2})/(\d{1,2})$')
_MESES_CURTO = (
    '', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
    'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
)


def _enriquecer_categoria(item) -> None:
    if item.tipo != 'compra':
        return
    cat = categoria_efetiva(item.descricao, item.categoria, item.tipo_compra)
    if cat and cat != item.categoria:
        item.categoria = cat


def agrupar_itens_por_cartao(fatura) -> list[dict]:
    itens = list(fatura.itens.all())
    for item in itens:
        _enriquecer_categoria(item)
    resumo_por_final = {
        str(r.get('final', '')): r
        for r in (fatura.cartoes_resumo or [])
        if r.get('final')
    }

    geral = [i for i in itens if not i.cartao_final]
    cartoes: dict[str, dict] = {}

    for item in itens:
        if not item.cartao_final:
            continue
        chave = item.cartao_final
        if chave not in cartoes:
            cartoes[chave] = {
                'final': chave,
                'portador': item.cartao_portador,
                'itens': [],
            }
        cartoes[chave]['itens'].append(item)
        if item.cartao_portador:
            cartoes[chave]['portador'] = item.cartao_portador

    grupos: list[dict] = []

    if geral:
        total_geral = sum((i.valor for i in geral), Decimal('0'))
        grupos.append({
            'id': 'movimentos',
            'titulo': 'Movimentos',
            'subtitulo': 'Saldo anterior, anuidade, pagamentos, juros e IOF',
            'itens': geral,
            'total': total_geral,
            'total_pdf': None,
        })

    for final in sorted(cartoes.keys()):
        bloco = cartoes[final]
        resumo = resumo_por_final.get(final, {})
        total_calc = sum((i.valor for i in bloco['itens']), Decimal('0'))
        portador = bloco['portador'] or resumo.get('portador', '')
        grupos.append({
            'id': f'cartao-{final}',
            'titulo': f'Gastos de {portador}' if portador else 'Gastos do cartão',
            'subtitulo': f'(final {final})',
            'final': final,
            'portador': portador,
            'itens': bloco['itens'],
            'total': total_calc,
            'total_pdf': _decimal_resumo(resumo.get('total_pdf')),
        })

    return grupos


def _itens_compras(itens) -> list:
    compras = [i for i in itens if i.tipo == 'compra']
    for item in compras:
        _enriquecer_categoria(item)
    return compras


def _total_compras(compras) -> Decimal:
    return sum((i.valor for i in compras), Decimal('0'))


def _percentual(valor: Decimal, total: Decimal) -> Decimal:
    if not total or total <= 0:
        return Decimal('0')
    return (valor / total * 100).quantize(Decimal('0.01'))


def resumir_por_fornecedor(itens) -> list[dict]:
    compras = _itens_compras(itens)
    total = _total_compras(compras)
    agg: dict[str, dict] = {}

    for item in compras:
        nome = (item.descricao or '').strip() or '—'
        if nome not in agg:
            agg[nome] = {
                'fornecedor': nome,
                'qtd': 0,
                'total': Decimal('0'),
            }
        agg[nome]['qtd'] += 1
        agg[nome]['total'] += item.valor

    linhas = sorted(agg.values(), key=lambda x: (-x['total'], x['fornecedor']))
    for linha in linhas:
        linha['percentual'] = _percentual(linha['total'], total)
    return linhas


def _parse_parcela(parcela: str) -> tuple[int, int] | None:
    m = _RE_PARCELA.match((parcela or '').strip())
    if not m:
        return None
    atual, total = int(m.group(1)), int(m.group(2))
    if total < 2 or atual < 1 or atual > total:
        return None
    return atual, total


def _base_vencimento_fatura(fatura) -> date:
    """Próxima fatura após a atual — base para projetar meses das parcelas."""
    if fatura is not None and getattr(fatura, 'vencimento', None):
        return fatura.vencimento
    hoje = date.today()
    dia = 1
    cartao = getattr(fatura, 'cartao', None) if fatura is not None else None
    if cartao and getattr(cartao, 'dia_vencimento_fatura', None):
        dia = int(cartao.dia_vencimento_fatura)
    try:
        return date(hoje.year, hoje.month, min(dia, 28))
    except ValueError:
        return hoje


def _rotulo_mes(d: date) -> str:
    return f'{_MESES_CURTO[d.month]}/{d.year}'


def _fmt_parcela(atual: int, total: int) -> str:
    return f'{atual:02d}/{total:02d}'


def resumir_parcelas_futuras(itens, fatura=None) -> dict:
    """Lançamentos parcelados com parcelas ainda a vencer nas próximas faturas.

    Também projeta cada parcela restante mês a mês (ex.: 02/10, 03/10…).
    """
    linhas: list[dict] = []
    por_mes: dict[str, dict] = {}

    base = _base_vencimento_fatura(fatura)

    for item in itens:
        if item.tipo != 'compra':
            continue
        parcela_txt = (item.parcela or '').strip()
        if not parcela_txt:
            m = _RE_PARCELA.search((item.descricao or '').strip())
            if m:
                parcela_txt = m.group(0)
        parsed = _parse_parcela(parcela_txt)
        if not parsed:
            continue
        atual, total = parsed
        if atual >= total:
            continue

        restantes = total - atual
        total_futuro = item.valor * restantes
        linhas.append({
            'descricao': item.descricao,
            'data': item.data,
            'parcela': parcela_txt,
            'parcela_atual': atual,
            'parcela_total': total,
            'parcelas_restantes': restantes,
            'valor_parcela': item.valor,
            'total_futuro': total_futuro,
            'cartao_final': item.cartao_final,
        })

        for offset in range(1, restantes + 1):
            venc = base + relativedelta(months=offset)
            chave = f'{venc.year:04d}-{venc.month:02d}'
            parcela_no_mes = atual + offset
            if chave not in por_mes:
                por_mes[chave] = {
                    'chave': chave,
                    'rotulo': _rotulo_mes(venc),
                    'vencimento': venc,
                    'linhas': [],
                    'total': Decimal('0'),
                    'qtd': 0,
                }
            por_mes[chave]['linhas'].append({
                'descricao': item.descricao,
                'data': item.data,
                'parcela': _fmt_parcela(parcela_no_mes, total),
                'parcela_atual': parcela_no_mes,
                'parcela_total': total,
                'valor_parcela': item.valor,
                'cartao_final': item.cartao_final,
            })
            por_mes[chave]['total'] += item.valor
            por_mes[chave]['qtd'] += 1

    linhas.sort(key=lambda x: (-x['total_futuro'], x['descricao']))
    meses = [por_mes[k] for k in sorted(por_mes.keys())]
    for mes in meses:
        mes['linhas'].sort(key=lambda x: (-x['valor_parcela'], x['descricao']))

    total_futuro = sum((l['total_futuro'] for l in linhas), Decimal('0'))
    total_parcelas = sum(l['parcelas_restantes'] for l in linhas)
    return {
        'linhas': linhas,
        'meses': meses,
        'total_futuro': total_futuro,
        'total_parcelas': total_parcelas,
        'qtd_compras': len(linhas),
    }


def _decimal_resumo(valor) -> Decimal | None:
    if valor is None or valor == '':
        return None
    try:
        return Decimal(str(valor))
    except Exception:
        return None


def resumo_cartoes_fatura(fatura) -> str:
    finais = []
    for r in fatura.cartoes_resumo or []:
        if r.get('final'):
            finais.append(str(r['final']))
    if not finais:
        finais = list(
            fatura.itens.exclude(cartao_final='').values_list('cartao_final', flat=True).distinct()
        )
    finais = sorted(set(f for f in finais if f))
    if len(finais) > 1:
        return f"{len(finais)} cartões ({', '.join(finais)})"
    if len(finais) == 1:
        return f"final {finais[0]}"
    if fatura.cartao_final:
        return f"final {fatura.cartao_final}"
    return ''
