"""Relatório de despesas pagas que se repetem (mesma descrição e dia do mês)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Q

from contasapagar.models import ContasaPagar


def _primeiro_dia_meses_atras(hoje: date, meses: int) -> date:
    """Primeiro dia do mês inicial ao olhar `meses` meses corridos (inclui o mês de `hoje`)."""
    m = hoje.month - (meses - 1)
    y = hoje.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _normalizar_descricao(texto: str | None) -> str:
    return ' '.join((texto or '').strip().upper().split())


def _valor_pago_conta(conta: ContasaPagar) -> Decimal:
    vp = conta.valorPago or Decimal('0')
    if vp > 0:
        return vp
    return conta.get_valor_total_com_ajustes()


def _fmt_moeda_br(valor: Decimal) -> str:
    s = f'{valor:.2f}'
    inteiro, cent = s.split('.')
    inteiro = f'{int(inteiro):,}'.replace(',', '.')
    return f'{inteiro},{cent}'


@dataclass
class PagamentoLinha:
    descricao: str
    descricao_exibir: str
    dia: int
    valor: Decimal
    data_pagamento: date
    conta_id: int


@dataclass
class GrupoDespesaRecorrente:
    descricao: str
    dia: int
    valores: list[Decimal] = field(default_factory=list)
    datas: list[date] = field(default_factory=list)
    quantidade: int = 0
    valor_total: Decimal = Decimal('0')
    valor_medio: Decimal = Decimal('0')
    meses_distintos: int = 0

    @property
    def valores_fmt(self) -> str:
        return ' · '.join(_fmt_moeda_br(v) for v in self.valores)

    @property
    def datas_fmt(self) -> str:
        return ', '.join(d.strftime('%d/%m/%Y') for d in self.datas)


def montar_pagamentos_periodo(
    empresa_id: int,
    *,
    data_inicio: date,
    data_fim: date,
    somente_tipo_despesa: bool = True,
) -> list[PagamentoLinha]:
    filtros = Q(
        empresa_id=empresa_id,
        status='pago',
        dtPag__gte=data_inicio,
        dtPag__lte=data_fim,
    )
    if somente_tipo_despesa:
        filtros &= Q(categoria__tipo='D')

    qs = (
        ContasaPagar.objects.filter(filtros)
        .exclude(dtPag__isnull=True)
        .only('id', 'descricao', 'dtPag', 'valorPago', 'valorDoc', 'juros', 'multa', 'desconto')
        .order_by('dtPag')
    )

    out: list[PagamentoLinha] = []
    for conta in qs:
        if not conta.dtPag:
            continue
        desc_norm = _normalizar_descricao(conta.descricao)
        if not desc_norm:
            continue
        out.append(
            PagamentoLinha(
                descricao=desc_norm,
                descricao_exibir=(conta.descricao or '').strip() or desc_norm,
                dia=conta.dtPag.day,
                valor=_valor_pago_conta(conta),
                data_pagamento=conta.dtPag,
                conta_id=conta.pk,
            )
        )
    return out


def agrupar_despesas_recorrentes(
    pagamentos: list[PagamentoLinha],
    *,
    min_ocorrencias: int = 2,
) -> list[GrupoDespesaRecorrente]:
    """
    Agrupa por descrição + dia do mês. Mantém apenas grupos com repetição
    (pelo menos `min_ocorrencias` pagamentos ou 2 meses distintos).
    """
    buckets: dict[tuple[str, int], list[PagamentoLinha]] = defaultdict(list)
    desc_exibir: dict[str, str] = {}
    for p in pagamentos:
        chave = (p.descricao, p.dia)
        buckets[chave].append(p)
        if p.descricao not in desc_exibir:
            desc_exibir[p.descricao] = p.descricao_exibir

    grupos: list[GrupoDespesaRecorrente] = []
    for (desc, dia), itens in buckets.items():
        itens_ord = sorted(itens, key=lambda x: x.data_pagamento)
        meses = {date(x.data_pagamento.year, x.data_pagamento.month, 1) for x in itens_ord}
        qtd = len(itens_ord)
        if qtd < min_ocorrencias and len(meses) < 2:
            continue
        valores = [x.valor for x in itens_ord]
        total = sum(valores, Decimal('0'))
        media = total / Decimal(qtd) if qtd else Decimal('0')
        grupos.append(
            GrupoDespesaRecorrente(
                descricao=desc_exibir.get(desc, desc),
                dia=dia,
                valores=valores,
                datas=[x.data_pagamento for x in itens_ord],
                quantidade=qtd,
                valor_total=total,
                valor_medio=media,
                meses_distintos=len(meses),
            )
        )

    grupos.sort(key=lambda g: (g.descricao.upper(), g.dia))
    return grupos


def montar_relatorio_despesas_recorrentes(
    empresa_id: int,
    *,
    hoje: date | None = None,
    meses: int = 4,
) -> dict:
    from django.utils import timezone

    hoje = hoje or timezone.localdate()
    data_inicio = _primeiro_dia_meses_atras(hoje, meses)
    pagamentos = montar_pagamentos_periodo(
        empresa_id,
        data_inicio=data_inicio,
        data_fim=hoje,
    )
    grupos = agrupar_despesas_recorrentes(pagamentos)
    return {
        'data_inicio': data_inicio,
        'data_fim': hoje,
        'meses': meses,
        'grupos': grupos,
        'total_grupos': len(grupos),
        'total_pagamentos': sum(g.quantidade for g in grupos),
    }


def exportar_xlsx_despesas_recorrentes(
    ctx: dict,
    destino,
    *,
    empresa_rotulo: str = '',
) -> str:
    """Grava relatório em arquivo .xlsx; retorna caminho absoluto."""
    from pathlib import Path

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = 'Despesas recorrentes'
    if empresa_rotulo:
        ws.append([f'Empresa: {empresa_rotulo}'])
        ws.append([f"Período: {ctx['data_inicio']:%d/%m/%Y} a {ctx['data_fim']:%d/%m/%Y}"])
        ws.append([])
    cab = ['Descrição', 'Dia', 'Quantidade', 'Valores', 'Datas pagamento', 'Total', 'Média']
    ws.append(cab)
    row_cab = ws.max_row
    for cell in ws[row_cab]:
        cell.font = Font(bold=True)
    for g in ctx['grupos']:
        ws.append([
            g.descricao,
            g.dia,
            g.quantidade,
            g.valores_fmt,
            g.datas_fmt,
            float(g.valor_total),
            float(g.valor_medio),
        ])
    path = Path(destino)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return str(path.resolve())


def caminhos_export_servidor(empresa_id: int, nome_arquivo: str) -> tuple:
    """Pasta media/exports/<empresa>/ e cópia fixa ultimo_…xlsx."""
    from pathlib import Path

    from django.conf import settings

    pasta = Path(settings.MEDIA_ROOT) / 'exports' / str(empresa_id)
    pasta.mkdir(parents=True, exist_ok=True)
    fixo = pasta / 'ultimo_despesas_recorrentes.xlsx'
    datado = pasta / nome_arquivo
    return fixo, datado, pasta


def resolver_empresa_id(termo: str) -> int | None:
    """Busca empresa por id numérico ou trecho da razão social / nome fantasia."""
    from django.db.models import Q

    from empresa.models import Empresa

    t = (termo or '').strip()
    if not t:
        return None
    if t.isdigit():
        return Empresa.objects.filter(pk=int(t)).values_list('pk', flat=True).first()
    qs = Empresa.objects.filter(
        Q(razao__icontains=t) | Q(nome_fantasia__icontains=t)
    ).order_by('id')
    return qs.values_list('pk', flat=True).first()