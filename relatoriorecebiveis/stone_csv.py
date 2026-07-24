"""
Parser do CSV de recebimentos Stone (exportação portal / extrato).
Delimitador ';', decimais pt-BR, UTF-8 com BOM.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def _norm_header(value: Any) -> str:
    if value is None:
        return ''
    s = str(value).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s)
    # N° / Nº → n
    s = s.replace('°', '').replace('º', '')
    return s


def _quantize_2(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    s = re.sub(r'[^\d,.\-]', '', s)
    if not s or s in ('-', '.', ',', '-.', '-,'):
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_date_str(value: Any) -> str:
    """Retorna data em dd/mm/yyyy (ignora hora se houver)."""
    if value is None:
        return ''
    s = str(value).strip()
    if not s:
        return ''
    # 17/06/2026 11:10 ou 17/07/2026
    for fmt in ('%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    # só a parte da data antes do espaço
    parte = s.split()[0] if ' ' in s else s
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(parte, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return parte


def _parse_int(value: Any, default: int = 1) -> int:
    if value is None or value == '':
        return default
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    m = re.search(r'\d+', s)
    return int(m.group(0)) if m else default


def _row_get(row: dict, *aliases: str) -> str:
    """Busca valor por cabeçalhos normalizados."""
    if not row:
        return ''
    norm_map = {_norm_header(k): (k, v) for k, v in row.items()}
    for alias in aliases:
        hit = norm_map.get(_norm_header(alias))
        if hit and hit[1] is not None and str(hit[1]).strip() != '':
            return str(hit[1]).strip()
    return ''


def _decode_csv_bytes(file_bytes: bytes) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode('utf-8', errors='replace')


def parse_stone_csv_bytes(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """
    Lê o CSV Stone e devolve linhas normalizadas + avisos.
    data_pagamento ← DATA DE VENCIMENTO
    numero_autorizacao ← STONE ID
    """
    warnings: list[str] = []
    text = _decode_csv_bytes(file_bytes)
    if not text.strip():
        return [], ['Arquivo vazio.']

    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    if not reader.fieldnames:
        return [], ['Cabeçalho não encontrado no CSV.']

    headers_norm = [_norm_header(h) for h in reader.fieldnames]
    required_any = {
        'data_pagamento': ('data de vencimento',),
        'valor_bruto': ('valor bruto',),
    }
    missing = []
    for key, aliases in required_any.items():
        if not any(a in headers_norm for a in aliases):
            missing.append(aliases[0])
    if missing:
        return [], [
            'Cabeçalho Stone não reconhecido. '
            f'Colunas obrigatórias ausentes: {", ".join(missing)}. '
            'Use o CSV de recebimentos exportado pela Stone (delimitador ;).'
        ]

    if 'stone id' not in headers_norm:
        warnings.append('Coluna STONE ID não encontrada — autorização ficará vazia.')

    out: list[dict] = []
    for row_num, row in enumerate(reader, start=2):
        if not row or all(not str(v or '').strip() for v in row.values()):
            continue

        categoria = _row_get(row, 'CATEGORIA')
        # Mantém vendas; avisa outras categorias mas ainda importa se tiver valor/data
        data_pag = _parse_date_str(_row_get(row, 'DATA DE VENCIMENTO'))
        if not data_pag:
            warnings.append(f'Linha {row_num}: data de vencimento ausente — ignorada')
            continue

        valor_bruto = _parse_decimal(_row_get(row, 'VALOR BRUTO'))
        if valor_bruto is None:
            warnings.append(f'Linha {row_num}: valor bruto ausente — ignorada')
            continue

        valor_liquido = _parse_decimal(_row_get(row, 'VALOR LÍQUIDO', 'VALOR LIQUIDO'))
        mdr = _parse_decimal(_row_get(row, 'DESCONTO DE MDR'))
        antecip = _parse_decimal(_row_get(row, 'DESCONTO DE ANTECIPAÇÃO', 'DESCONTO DE ANTECIPACAO'))
        taxa = Decimal('0')
        if mdr is not None:
            taxa += abs(mdr)
        if antecip is not None:
            taxa += abs(antecip)
        if valor_liquido is None:
            valor_liquido = valor_bruto - taxa

        valor_bruto = _quantize_2(valor_bruto)
        valor_liquido = _quantize_2(valor_liquido)
        taxa = _quantize_2(taxa)

        produto = _row_get(row, 'PRODUTO')
        produto_l = produto.lower()
        is_debito = 'debito' in produto_l or 'débito' in produto_l

        total_parcelas = _parse_int(_row_get(row, 'QTD DE PARCELAS'), 1)
        numero_parcela = _parse_int(
            _row_get(row, 'N DA PARCELA', 'N° DA PARCELA', 'Nº DA PARCELA', 'NUMERO DA PARCELA'),
            1,
        )
        if is_debito and total_parcelas <= 1:
            numero_parcela = 1
            total_parcelas = 1

        stone_id = _row_get(row, 'STONE ID', 'STONEID')
        stonecode = _row_get(row, 'STONECODE')
        documento = _row_get(row, 'DOCUMENTO')
        data_venda = _parse_date_str(_row_get(row, 'DATA DA VENDA'))

        out.append({
            'linha': row_num - 1,
            'data_pagamento': data_pag,
            'forma_pagamento': produto,
            'bandeira': _row_get(row, 'BANDEIRA'),
            'valor_bruto': f'{valor_bruto:.2f}',
            'taxa_maquinha': f'{taxa:.2f}',
            'valor_liquido': f'{valor_liquido:.2f}',
            'maquinha': 'STONE',
            'numero_autorizacao': stone_id,
            'data_venda': data_venda,
            'nsu_doc': stone_id or stonecode,
            'parcelas': str(numero_parcela),
            'total_parcelas': str(total_parcelas),
            'parcela_texto': f'{numero_parcela} / {total_parcelas}',
            'conciliado': 'Não',
            'nota_fiscal': '',
            'razao': documento,
            'conta_bancaria': f'StoneCode {stonecode}' if stonecode else '',
            'categoria': categoria,
            'stonecode': stonecode,
            'status_pagamento': _row_get(row, 'ÚLTIMO STATUS', 'ULTIMO STATUS'),
        })

    if not out and not warnings:
        warnings.append('Nenhuma linha de recebimento encontrada no arquivo.')
    return out, warnings
