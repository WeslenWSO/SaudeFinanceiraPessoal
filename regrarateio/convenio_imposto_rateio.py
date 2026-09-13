"""Lança impostos de apuração (total convênio) como PGTO no rateio."""
import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction

from regrarateio.convenio_viabilidade import coletar_totais_por_viabilidade_convenio
from regrarateio.models import LancamentoRateio, RegraRateioItem
from regrarateio.services import (
    _calcular_valores_por_socio,
    _regra_forcada_validada,
    _validar_estrutura_regra,
)

IMPOSTOS_CONVENIO = (
    ('ISS', 'iss_ap'),
    ('PIS', 'pis_ap'),
    ('COFINS', 'cofins_ap'),
    ('CSLL', 'csll_ap'),
    ('IRPJ', 'irpj_mais_ad'),
)

# Dia do pagamento no mês de referência (competência do filtro).
IMPOSTO_DIA_PAGAMENTO = {
    'ISS': 15,
    'PIS': 25,
    'COFINS': 25,
    'CSLL': 30,
    'IRPJ': 30,
}


def mes_referencia_unico(data_inicio: date | None, data_fim: date | None) -> tuple[int, int] | None:
    if not data_inicio or not data_fim:
        return None
    if data_inicio.year != data_fim.year or data_inicio.month != data_fim.month:
        return None
    return data_inicio.year, data_inicio.month


def _chave_periodo(data_inicio: date | None, data_fim: date | None) -> str:
    ref = mes_referencia_unico(data_inicio, data_fim)
    if ref:
        ano, mes = ref
        return f'{ano:04d}-{mes:02d}'
    parts = []
    if data_inicio:
        parts.append(data_inicio.isoformat())
    if data_fim:
        parts.append(data_fim.isoformat())
    return '_'.join(parts) if parts else 'sem_periodo'


def _rotulo_periodo(data_inicio: date | None, data_fim: date | None) -> str:
    meses = (
        '', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
        'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
    )
    ref = mes_referencia_unico(data_inicio, data_fim)
    if ref:
        ano, mes = ref
        return f'{meses[mes]}/{ano}'
    if data_inicio and data_fim:
        return f'{data_inicio.strftime("%d/%m/%Y")} a {data_fim.strftime("%d/%m/%Y")}'
    if data_fim:
        return data_fim.strftime('%d/%m/%Y')
    if data_inicio:
        return data_inicio.strftime('%d/%m/%Y')
    return 'período do filtro'


def _obs_marcador(chave_periodo: str, imposto: str) -> str:
    return f'TOTAL_CONVENIO:{chave_periodo}:{imposto}'


def _valor_imposto(totais: dict, campo: str) -> Decimal:
    if campo == 'irpj_mais_ad':
        return totais.get('total_irpj_mais_ad') or Decimal('0')
    cols = totais.get('totais_colunas') or {}
    val = cols.get(campo)
    if val is None:
        return Decimal('0')
    return val if isinstance(val, Decimal) else Decimal(str(val))


def impostos_convenio_ja_lancados(empresa_id, chave_periodo: str) -> list[str]:
    prefix = f'TOTAL_CONVENIO:{chave_periodo}:'
    qs = LancamentoRateio.objects.filter(
        empresa_id=empresa_id,
        origem=LancamentoRateio.ORIGEM_TOTAL_CONVENIO,
        obs__startswith=prefix,
    ).values_list('obs', flat=True).distinct()
    return sorted({obs.split(':', 2)[-1] for obs in qs if obs})


def impostos_pendentes_lancamento(totais: dict, ja_lancados: list[str]) -> list[str]:
    ja = set(ja_lancados)
    pendentes = []
    for imposto, campo in IMPOSTOS_CONVENIO:
        if _valor_imposto(totais, campo) > 0 and imposto not in ja:
            pendentes.append(imposto)
    return pendentes


def _data_pagamento_imposto(imposto: str, ano: int, mes: int) -> date:
    dia = IMPOSTO_DIA_PAGAMENTO.get(imposto, 30)
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia, ultimo))


def _descricao_imposto(imposto: str, ano: int, mes: int) -> str:
    return f'REF A {imposto} COMP {mes:02d}/{ano}'


def _gerar_linhas_imposto(
    *,
    empresa_id,
    regra,
    itens,
    imposto: str,
    base: Decimal,
    data_pg: date,
    chave_periodo: str,
    ano: int,
    mes: int,
) -> int:
    if base <= 0:
        return 0
    if LancamentoRateio.objects.filter(
        empresa_id=empresa_id,
        origem=LancamentoRateio.ORIGEM_TOTAL_CONVENIO,
        obs=_obs_marcador(chave_periodo, imposto),
    ).exists():
        return 0
    valores = _calcular_valores_por_socio(regra, itens, base)
    desc = _descricao_imposto(imposto, ano, mes)[:255]
    obs = _obs_marcador(chave_periodo, imposto)
    criados = 0
    for item in itens:
        bruto = valores.get(item.socios_id, Decimal('0'))
        if bruto <= 0:
            continue
        valor = -bruto.quantize(Decimal('0.01'))
        LancamentoRateio.objects.create(
            empresa_id=empresa_id,
            conta_pagar=None,
            conta_receber=None,
            data_pagamento=data_pg,
            tipo=LancamentoRateio.TIPO_DEDUCAO_RECEITA,
            descricao=desc,
            regra_rateio=regra,
            socio=item.socios,
            valor=valor,
            origem=LancamentoRateio.ORIGEM_TOTAL_CONVENIO,
            obs=obs,
        )
        criados += 1
    return criados


@transaction.atomic
def gerar_rateio_impostos_total_convenio(
    *,
    empresa_id,
    regra_id,
    qs_filtro,
    data_inicio: date | None,
    data_fim: date | None,
    periodo_ad_irpj: str = 'mensal',
) -> tuple[int, list[str], list[str]]:
    """
    Cria lançamentos PGTO (origem TOTAL CONVENIO) para ISS, PIS, COFINS, CSLL e IRPJ
    (IRPJ ap. + Ad. IRPJ) com base nos totais do modal de convênios.

    Retorna (criados, impostos_lancados, impostos_ignorados).
    """
    ref = mes_referencia_unico(data_inicio, data_fim)
    if not ref:
        raise ValueError(
            'Para lançar impostos, filtre um único mês (ex.: 01/06/2026 a 30/06/2026).'
        )

    regra = _regra_forcada_validada(regra_id, empresa_id)
    if not regra:
        raise ValueError('Selecione uma regra de rateio.')

    totais = coletar_totais_por_viabilidade_convenio(
        empresa_id, qs_filtro, periodo_ad_irpj=periodo_ad_irpj
    )
    if not totais.get('linhas'):
        raise ValueError('Nenhuma receita com convênio cadastrado no filtro atual.')

    ano, mes = ref
    chave = _chave_periodo(data_inicio, data_fim)
    rotulo = _rotulo_periodo(data_inicio, data_fim)
    ja = set(impostos_convenio_ja_lancados(empresa_id, chave))

    itens = list(RegraRateioItem.objects.filter(regrarateio=regra).select_related('socios'))
    _validar_estrutura_regra(regra, itens)

    criados = 0
    lancados: list[str] = []
    ignorados: list[str] = []

    for imposto, campo in IMPOSTOS_CONVENIO:
        base = _valor_imposto(totais, campo)
        if base <= 0:
            continue
        if imposto in ja:
            ignorados.append(imposto)
            continue
        data_pg = _data_pagamento_imposto(imposto, ano, mes)
        n = _gerar_linhas_imposto(
            empresa_id=empresa_id,
            regra=regra,
            itens=itens,
            imposto=imposto,
            base=base,
            data_pg=data_pg,
            chave_periodo=chave,
            ano=ano,
            mes=mes,
        )
        if n:
            criados += n
            lancados.append(imposto)
        elif imposto in ja:
            ignorados.append(imposto)

    if not lancados and ignorados:
        raise ValueError(
            f'Impostos já lançados em {rotulo}: {", ".join(ignorados)}. '
            'Não é permitido duplicar no mesmo mês.'
        )
    if not lancados and not ignorados:
        raise ValueError('Nenhum imposto com valor maior que zero para lançar.')

    return criados, lancados, ignorados
