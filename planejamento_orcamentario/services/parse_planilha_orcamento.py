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


def _normalizar_mes(texto: str) -> str:
    t = unicodedata.normalize('NFKD', (texto or '').strip().upper())
    return ''.join(c for c in t if not unicodedata.combining(c))


def parse_como_gerar(texto: str) -> tuple[int, date]:
    """
    Ex.: 'GERAR AS PARCELAS 28 ATE 36 APARTIR DE SETEMBRO/2026'
    Retorna (qtd_meses, data_inicio) — data_inicio usa dia informado separadamente.
    """
    m = _RE_COMO_GERAR.search(texto or '')
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
    return qtd_meses, date(ano, mes, 1)


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


def tipo_por_observacao(observacao: str) -> str:
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


def montar_item_da_linha(
    *,
    dia: int,
    fornecedor: str,
    valor_mensal,
    como_gerar: str,
    categoria_nome: str,
    observacao: str = '',
    ocorrencias: str = 'MENSAL',
) -> dict:
    qtd_meses, ref = parse_como_gerar(como_gerar)
    data_inicio = data_inicio_com_dia(dia, ref.month, ref.year)
    return {
        'nome': (fornecedor or '').strip(),
        'tipo': tipo_por_observacao(observacao),
        'observacao': (observacao or ocorrencias or '').strip(),
        'valor_mensal': parse_valor_br(valor_mensal),
        'data_inicio': data_inicio,
        'qtd_meses': qtd_meses,
        'categoria_busca': (categoria_nome or '').strip(),
        'forma_calculo': ItemOrcamento.FORMA_FIXO,
    }
