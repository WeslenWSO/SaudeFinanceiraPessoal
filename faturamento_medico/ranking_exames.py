"""Ranking de exames (procedimentos) e valores por convênio/parceiro no período filtrado."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from faturamento_medico.lote_relatorio import _modalidade_item
from faturamento_medico.models import FaturamentoMedico


def _label_convenio(nome: str | None) -> str:
    n = (nome or '').strip()
    if not n:
        return 'Particular / não informado'
    if n.lower() in ('particular', 'part'):
        return 'Particular'
    return n


def _valor_item(item, faturamento) -> Decimal:
    if item is not None:
        raw = item.total if item.total is not None else item.valor
    else:
        raw = faturamento.total
    try:
        return Decimal(str(raw or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def _exame_passa_filtro(nome_exame: str, exames_filtro: list[str]) -> bool:
    if not exames_filtro:
        return True
    ex = (nome_exame or '').strip()
    return any(ex.lower() == f.strip().lower() for f in exames_filtro if f and str(f).strip())


def _codigo_modalidade_item(faturamento, item=None) -> str:
    bruto = (_modalidade_item(faturamento, item) or '').strip().upper()
    if bruto == 'RX':
        bruto = 'CR'
    if not bruto or bruto == '-':
        return 'OUTROS'
    return bruto


def _modalidade_passa_filtro(faturamento, item, modalidades_filtro: list[str]) -> bool:
    if not modalidades_filtro:
        return True
    cod = _codigo_modalidade_item(faturamento, item)
    return cod in modalidades_filtro


def montar_ranking_exames_qs(
    faturamentos_qs,
    *,
    exames_filtro: list[str] | None = None,
    modalidades_filtro: list[str] | None = None,
) -> dict:
    """
    Agrega itens de serviço do queryset (já filtrado por data/convênio/etc.).
    Retorna ranking por exame, por convênio e detalhe exame × convênio.
    """
    exames_filtro = [e for e in (exames_filtro or []) if e and str(e).strip()]
    modalidades_filtro = [m for m in (modalidades_filtro or []) if m and str(m).strip()]
    por_exame: dict[str, dict] = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})
    por_convenio: dict[str, dict] = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})
    detalhe: list[dict] = []
    chaves_detalhe: dict[tuple[str, str], dict] = {}

    qs = faturamentos_qs.prefetch_related('itens_servico').order_by('data', 'id')
    for fat in qs:
        conv = _label_convenio(fat.convenio)
        itens = list(fat.itens_servico.all())
        if not itens:
            proc = (getattr(fat, 'servico', None) or '').strip() or 'Não informado'
            if not _exame_passa_filtro(proc, exames_filtro):
                continue
            if not _modalidade_passa_filtro(fat, None, modalidades_filtro):
                continue
            val = _valor_item(None, fat)
            por_exame[proc]['quantidade'] += 1
            por_exame[proc]['valor'] += val
            por_convenio[conv]['quantidade'] += 1
            por_convenio[conv]['valor'] += val
            chave = (proc, conv)
            if chave not in chaves_detalhe:
                chaves_detalhe[chave] = {'exame': proc, 'convenio': conv, 'quantidade': 0, 'valor': Decimal('0')}
            chaves_detalhe[chave]['quantidade'] += 1
            chaves_detalhe[chave]['valor'] += val
            continue

        for item in itens:
            proc = (item.servico or '').strip() or 'Não informado'
            if not _exame_passa_filtro(proc, exames_filtro):
                continue
            if not _modalidade_passa_filtro(fat, item, modalidades_filtro):
                continue
            val = _valor_item(item, fat)
            por_exame[proc]['quantidade'] += 1
            por_exame[proc]['valor'] += val
            por_convenio[conv]['quantidade'] += 1
            por_convenio[conv]['valor'] += val
            chave = (proc, conv)
            if chave not in chaves_detalhe:
                chaves_detalhe[chave] = {'exame': proc, 'convenio': conv, 'quantidade': 0, 'valor': Decimal('0')}
            chaves_detalhe[chave]['quantidade'] += 1
            chaves_detalhe[chave]['valor'] += val

    ranking_exames = sorted(
        [
            {'exame': k, 'quantidade': v['quantidade'], 'valor': v['valor']}
            for k, v in por_exame.items()
        ],
        key=lambda r: (-int(r['quantidade']), -float(r['valor']), r['exame'].lower()),
    )
    ranking_convenios = sorted(
        [
            {'convenio': k, 'quantidade': v['quantidade'], 'valor': v['valor']}
            for k, v in por_convenio.items()
        ],
        key=lambda r: (-float(r['valor']), -int(r['quantidade']), r['convenio'].lower()),
    )
    detalhe = sorted(
        chaves_detalhe.values(),
        key=lambda r: (r['exame'].lower(), -float(r['valor']), r['convenio'].lower()),
    )

    total_qtd = sum(r['quantidade'] for r in ranking_exames)
    total_valor = sum((r['valor'] for r in ranking_exames), Decimal('0'))

    return {
        'ranking_exames': ranking_exames,
        'ranking_convenios': ranking_convenios,
        'detalhe_exame_convenio': detalhe,
        'total_quantidade': total_qtd,
        'total_valor': total_valor,
    }
