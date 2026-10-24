"""Relatório de validação por status de conferência (aba Análises)."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from faturamento_medico.dashboard_exames import MESES_PT, _status_linha
from faturamento_medico.models import FaturamentoMedico
from faturamento_medico.ranking_exames import _valor_item

from dashboard.analise_faturamento_convenio import (
    _fmt_moeda,
    _fmt_numero_int,
    _q_cancelados,
)
from dashboard.analises_conferencia import (
    STATUS_CONFERENCIA_INCLUIDOS_ANALISE,
    ids_lotes_empresa,
    item_conta_faturamento_analise,
    rotulo_status_analise,
)


def montar_relatorio_validacao_conferencia(empresa_id: int, ano: int, mes: int) -> dict:
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    ids_internos = ids_lotes_empresa(empresa_id)

    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=inicio,
            data__lte=fim,
        )
        .exclude(_q_cancelados())
        .prefetch_related('itens_servico')
    )

    por_status: dict[str, dict] = defaultdict(lambda: {'quantidade': 0, 'valor': Decimal('0')})
    incluidos_qtd = 0
    incluidos_valor = Decimal('0')
    excluidos_qtd = 0
    excluidos_valor = Decimal('0')

    for fat in qs:
        itens = list(fat.itens_servico.all())
        blocos = [(None, fat)] if not itens else [(item, fat) for item in itens]
        for item, faturamento in blocos:
            status, _ = _status_linha(faturamento, item, ids_internos=ids_internos)
            valor = _valor_item(item, faturamento)
            por_status[status]['quantidade'] += 1
            por_status[status]['valor'] += valor
            if item_conta_faturamento_analise(faturamento, item, ids_internos=ids_internos):
                incluidos_qtd += 1
                incluidos_valor += valor
            else:
                excluidos_qtd += 1
                excluidos_valor += valor

    linhas = []
    for status, dados in sorted(
        por_status.items(),
        key=lambda x: (-float(x[1]['valor']), -x[1]['quantidade'], x[0]),
    ):
        linhas.append({
            'status': status,
            'rotulo': rotulo_status_analise(status),
            'incluido_analise': status in STATUS_CONFERENCIA_INCLUIDOS_ANALISE,
            'quantidade': dados['quantidade'],
            'valor': dados['valor'],
            'quantidade_fmt': _fmt_numero_int(dados['quantidade']),
            'valor_fmt': _fmt_moeda(dados['valor']),
        })

    mes_titulo = f'{MESES_PT[mes].upper()} {ano}'
    return {
        'titulo_relatorio': f'VALIDAÇÃO — STATUS DE CONFERÊNCIA — {mes_titulo}',
        'subtitulo_periodo': (
            'Incluídos nas demais análises: Aguardando o faturamento (CONFERIDO) e '
            'Concluído (LOTE OK). Demais status não entram no faturamento das análises.'
        ),
        'linhas_status': linhas,
        'incluidos_quantidade_fmt': _fmt_numero_int(incluidos_qtd),
        'incluidos_valor_fmt': _fmt_moeda(incluidos_valor),
        'excluidos_quantidade_fmt': _fmt_numero_int(excluidos_qtd),
        'excluidos_valor_fmt': _fmt_moeda(excluidos_valor),
    }
