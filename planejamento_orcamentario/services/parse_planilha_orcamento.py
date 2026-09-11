"""Interpreta colunas da planilha de planejamento (DIA, COMO GERAR, etc.)."""

from __future__ import annotations

import re
import unicodedata
from calendar import monthrange
from datetime import date
from decimal import Decimal

from planejamento_orcamentario.models import ItemOrcamento

_MESES_PT = {
    'JANEIRO': 1,
    'FEVEREIRO': 2,
    'MARCO': 3,
    'MARÇO': 3,
    'ABRIL': 4,
    'MAIO': 5,
    'JUNHO': 6,
    'JULHO': 7,
    'AGOSTO': 8,
    'SETEMBRO': 9,
    'OUTUBRO': 10,
    'NOVEMBRO': 11,
    'DEZEMBRO': 12,
}

_RE_COMO_GERAR = re.compile(
    r'GERAR\s+AS?\s+PARCELAS?\s+(\d+)\s+ATE\s+(\d+)\s+APARTIR\s+DE\s+'
    r'([A-ZÇÁÉÍÓÚÃÕ]+)\s*/\s*(\d{4})',
    re.IGNORECASE,
)

_RE_PROXIMOS_MESES = re.compile(
    r'GERAR\s+OS?\s+PROXIMOS?\s+(\d+)\s+MESES?\s+COMECANDO\s+(\d{1,2})\s*/\s*(\d{4})',
    re.IGNORECASE,
)


def _normalizar_mes(texto: str) -> str:
    t = unicodedata.normalize('NFKD', (texto or '').strip().upper())
    return ''.join(c for c in t if not unicodedata.combining(c))


def parse_como_gerar(texto: str) -> tuple[int, date, int]:
    """
    Interpreta instrução de geração.
    Retorna (qtd_meses, ref_mes_ano, intervalo_meses).
    """
    texto = (texto or '').strip()
    m = _RE_PROXIMOS_MESES.search(texto)
    if m:
        qtd_meses = int(m.group(1))
        mes = int(m.group(2))
        ano = int(m.group(3))
        if not 1 <= mes <= 12:
            raise ValueError(f'Mês inválido em COMO GERAR: {m.group(2)!r}')
        return qtd_meses, date(ano, mes, 1), 1

    m = _RE_COMO_GERAR.search(texto)
    if not m:
        raise ValueError(f'Coluna COMO GERAR inválida: {texto!r}')
    parcela_ini = int(m.group(1))
    parcela_fim = int(m.group(2))
    mes_nome = _normalizar_mes(m.group(3))
    ano = int(m.group(4))
    mes = _MESES_PT.get(mes_nome)
    if not mes:
        raise ValueError(f'Mês não reconhecido em COMO GERAR: {m.group(3)!r}')
    if parcela_fim < parcela_ini:
        raise ValueError(f'Parcela final ({parcela_fim}) menor que inicial ({parcela_ini}).')
    qtd_meses = parcela_fim - parcela_ini + 1
    return qtd_meses, date(ano, mes, 1), 1


def intervalo_por_ocorrencia(ocorrencias: str) -> int:
    occ = (ocorrencias or 'MENSAL').strip().upper()
    if occ.startswith('TRIM'):
        return 3
    if occ.startswith('SEM'):
        return 6
    if occ.startswith('ANU') or occ.startswith('ANUAL'):
        return 12
    return 1


def data_inicio_com_dia(dia: int, mes: int, ano: int) -> date:
    dia = max(1, int(dia))
    dia = min(dia, monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def parse_valor_br(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor.quantize(Decimal('0.01'))
    s = str(valor or '').strip()
    if not s:
        return Decimal('0.00')
    s = s.replace('R$', '').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    return Decimal(s).quantize(Decimal('0.01'))


def tipo_por_observacao(observacao: str, impostos: str = '') -> str:
    imp = (impostos or '').strip().upper()
    if imp in ('SIM', 'S', 'YES', '1'):
        return ItemOrcamento.TIPO_IMPOSTO
    obs = (observacao or '').strip().lower()
    if 'semi-fix' in obs or 'semi fix' in obs:
        return ItemOrcamento.TIPO_SEMI_FIXA
    if 'vari' in obs:
        return ItemOrcamento.TIPO_VARIAVEL
    if 'imposto' in obs or 'tribut' in obs:
        return ItemOrcamento.TIPO_IMPOSTO
    if 'receita' in obs:
        return ItemOrcamento.TIPO_RECEITA
    return ItemOrcamento.TIPO_FIXA


def gerar_lancamentos_intervalo(item, intervalo_meses: int = 1) -> int:
    """Gera lançamentos a cada N meses dentro de qtd_meses (ex.: trimestral = 3)."""
    from planejamento_orcamentario.models import LancamentoOrcamento, _add_months

    item.lancamentos.all().delete()
    if not item.data_inicio:
        return 0
    horizonte = max(1, int(item.qtd_meses or 1))
    intervalo = max(1, int(intervalo_meses or 1))
    criar = []
    seq = 0
    for offset in range(0, horizonte, intervalo):
        seq += 1
        criar.append(
            LancamentoOrcamento(
                item=item,
                empresa=item.empresa,
                data_lancamento=_add_months(item.data_inicio, offset),
                valor=item.valor_mensal or Decimal('0'),
                sequencia=seq,
            )
        )
    LancamentoOrcamento.objects.bulk_create(criar)
    return len(criar)


def montar_item_da_linha(
    *,
    dia: int,
    fornecedor: str,
    valor_mensal,
    como_gerar: str,
    categoria_nome: str,
    observacao: str = '',
    ocorrencias: str = 'MENSAL',
    impostos: str = '',
) -> dict:
    qtd_meses, ref, _intervalo_instrucao = parse_como_gerar(como_gerar)
    intervalo_meses = intervalo_por_ocorrencia(ocorrencias)
    data_inicio = data_inicio_com_dia(dia, ref.month, ref.year)
    obs_partes = [p for p in ((observacao or '').strip(), (ocorrencias or '').strip()) if p]
    return {
        'nome': (fornecedor or '').strip(),
        'tipo': tipo_por_observacao(observacao, impostos),
        'observacao': ' · '.join(obs_partes),
        'valor_mensal': parse_valor_br(valor_mensal),
        'data_inicio': data_inicio,
        'qtd_meses': qtd_meses,
        'intervalo_meses': intervalo_meses,
        'categoria_busca': (categoria_nome or '').strip(),
        'forma_calculo': ItemOrcamento.FORMA_FIXO,
    }
