"""Importação de relatório UNIMED (.txt ou .pdf — Produção)."""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from typing import Any

import pdfplumber
from django.utils import timezone

from faturamento_medico.models import FaturamentoMedico, ItemServico
from servicos_medicos.models import ServicosMedicos

def _fold(s: str) -> str:
    if not s:
        return ''
    d = unicodedata.normalize('NFKD', str(s))
    d = ''.join(c for c in d if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', d).strip().lower()


def _money_br(raw: str) -> float:
    s = (raw or '').strip()
    if not s:
        return 0.0
    s = s.replace('R$', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_data(raw: str):
    s = (raw or '').strip()
    if not s:
        return timezone.now().date()
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return timezone.now().date()


def _parse_int(raw: str) -> int:
    s = (raw or '').strip().replace(',', '.')
    if not s:
        return 1
    try:
        return int(float(s))
    except ValueError:
        return 1


def _linha_ignorada(cells: list[str]) -> bool:
    blob = _fold(' '.join(cells))
    if not blob:
        return True
    if 'tipo de guia' in blob:
        return True
    if 'vl. total pago' in blob or 'valor total pago' in blob:
        return True
    if blob in ('producao', 'produção'):
        return True
    if blob.startswith('lote guia'):
        return True
    return False


def _mapear_colunas_pdf(headers: list[str]) -> dict[str, int | None]:
    folded = [_fold(h) for h in headers]
    col_map: dict[str, int | None] = {
        'lote': None,
        'guia': None,
        'cod_usuario': None,
        'nome_usuario': None,
        'cod_servico': None,
        'desc_servico': None,
        'guia_prest': None,
        'data': None,
        'qtde': None,
        'via': None,
        'valor_unit': None,
        'valor_total': None,
    }

    for i, h in enumerate(folded):
        if not h:
            continue
        if h == 'lote' or h.startswith('lote '):
            col_map['lote'] = i
        elif h == 'guia':
            col_map['guia'] = i
        elif 'guia prest' in h:
            col_map['guia_prest'] = i
        elif 'cod' in h and 'usuario' in h:
            col_map['cod_usuario'] = i
        elif 'nome' in h and 'usuario' in h:
            col_map['nome_usuario'] = i
        elif 'cod' in h and 'serv' in h:
            col_map['cod_servico'] = i
        elif 'desc' in h and 'serv' in h:
            col_map['desc_servico'] = i
        elif h == 'data':
            col_map['data'] = i
        elif h.startswith('qtde') or h == 'qt':
            col_map['qtde'] = i
        elif h == 'via':
            col_map['via'] = i
        elif 'valor unit' in h:
            col_map['valor_unit'] = i
        elif 'valor (r$)' in h or h == 'valor r$' or (h.startswith('valor') and 'r$' in h):
            col_map['valor_total'] = i

    return col_map


def _cel(cells: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(cells):
        return ''
    return str(cells[idx] or '').strip()


def _adicionar_linha_grupo(
    grupos: dict[str, dict[str, Any]],
    servicos_unicos: set[tuple[str, str]],
    *,
    lote: str,
    guia: str,
    cod_usuario: str,
    nome_usuario: str,
    cod_servico: str,
    desc_servico: str,
    data,
    qtde: int,
    valor_unit: float,
    valor_total: float,
    cod_rel: str = '',
    observacao: str = '',
    porte: str = '',
    percentual: float = 0,
) -> None:
    if not lote or not guia or not cod_servico:
        return

    chave = f'{lote}_{guia}'
    if chave not in grupos:
        grupos[chave] = {
            'lote': lote,
            'guia': guia,
            'carteirinha': cod_usuario,
            'nome': nome_usuario,
            'data': data,
            'cod_rel': cod_rel,
            'servicos': [],
        }

    grupos[chave]['servicos'].append({
        'codigo': cod_servico,
        'descricao': desc_servico,
        'porte': porte,
        'qt': qtde,
        'percentual': percentual,
        'valor': valor_unit,
        'total': valor_total,
        'observacao': observacao,
    })
    servicos_unicos.add((cod_servico, desc_servico))


def parse_unimed_txt(content: str) -> tuple[dict[str, dict], set[tuple[str, str]]]:
    """Arquivo .txt separado por ponto e vírgula (cabeçalho na 1ª linha)."""
    grupos: dict[str, dict] = {}
    servicos_unicos: set[tuple[str, str]] = set()
    lines = content.splitlines()

    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(';')
        if len(parts) < 13:
            continue

        lote = parts[0].strip()
        guia = parts[1].strip()
        cod_usuario = parts[2].strip()
        nome_usuario = parts[3].strip()
        cod_servico = parts[5].strip()
        desc_servico = parts[6].strip()
        tp_grau = parts[7].strip()
        data = _parse_data(parts[8].strip())
        qtde_via = parts[9].strip()
        percentual = _money_br(parts[10].strip())
        valor_unit = _money_br(parts[11].strip())
        valor_total = _money_br(parts[12].strip())
        cod_rel = parts[13].strip() if len(parts) > 13 else ''
        observacao = parts[14].strip() if len(parts) > 14 else ''

        _adicionar_linha_grupo(
            grupos,
            servicos_unicos,
            lote=lote,
            guia=guia,
            cod_usuario=cod_usuario,
            nome_usuario=nome_usuario,
            cod_servico=cod_servico,
            desc_servico=desc_servico,
            data=data,
            qtde=_parse_int(qtde_via),
            valor_unit=valor_unit,
            valor_total=valor_total,
            cod_rel=cod_rel,
            observacao=observacao,
            porte=tp_grau,
            percentual=percentual,
        )

    return grupos, servicos_unicos


def _parse_unimed_pdf_table(table: list[list[Any]], col_map: dict[str, int | None]) -> tuple[dict, set]:
    grupos: dict[str, dict] = {}
    servicos_unicos: set[tuple[str, str]] = set()

    for row in table:
        cells = [str(c or '').strip() for c in row]
        if _linha_ignorada(cells):
            continue

        lote = _cel(cells, col_map.get('lote'))
        guia = _cel(cells, col_map.get('guia'))
        if not lote.isdigit() or not guia.isdigit():
            continue

        cod_usuario = _cel(cells, col_map.get('cod_usuario'))
        nome_usuario = _cel(cells, col_map.get('nome_usuario'))
        cod_servico = _cel(cells, col_map.get('cod_servico'))
        desc_servico = _cel(cells, col_map.get('desc_servico'))
        guia_prest = _cel(cells, col_map.get('guia_prest'))
        data = _parse_data(_cel(cells, col_map.get('data')))
        qtde = _parse_int(_cel(cells, col_map.get('qtde')))
        valor_unit = _money_br(_cel(cells, col_map.get('valor_unit')))
        valor_total = _money_br(_cel(cells, col_map.get('valor_total')))

        obs_parts = []
        if guia_prest:
            obs_parts.append(f'Guia prest.: {guia_prest}')
        via = _cel(cells, col_map.get('via'))
        if via:
            obs_parts.append(f'Via: {via}')

        _adicionar_linha_grupo(
            grupos,
            servicos_unicos,
            lote=lote,
            guia=guia,
            cod_usuario=cod_usuario,
            nome_usuario=nome_usuario,
            cod_servico=cod_servico,
            desc_servico=desc_servico,
            data=data,
            qtde=qtde,
            valor_unit=valor_unit,
            valor_total=valor_total,
            observacao=' | '.join(obs_parts),
        )

    return grupos, servicos_unicos


def _merge_grupos(
    base: dict[str, dict],
    extra: dict[str, dict],
    servicos_base: set[tuple[str, str]],
    servicos_extra: set[tuple[str, str]],
) -> tuple[dict[str, dict], set[tuple[str, str]]]:
    for chave, dados in extra.items():
        if chave not in base:
            base[chave] = dados
        else:
            base[chave]['servicos'].extend(dados['servicos'])
    servicos_base.update(servicos_extra)
    return base, servicos_base


def _parse_linha_pdf_texto(line: str) -> dict[str, Any] | None:
    """Fallback: linha de texto extraída do PDF (relatório Produção)."""
    line = re.sub(r'\s+', ' ', (line or '').strip())
    if _linha_ignorada([line]):
        return None

    m_data = re.search(r'(\d{2}/\d{2}/\d{4})', line)
    if not m_data:
        return None

    left = line[: m_data.start()].strip()
    right = line[m_data.end() :].strip()
    data_str = m_data.group(1)

    lm = re.match(
        r'^(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s+[A-Z]\s+(\d+)\s+(.+?)\s+(\d+)\s+(\w+)\s*$',
        left,
    )
    if not lm:
        return None

    rm = re.match(
        r'^(\d+)\s+(\d+)\s+[\d.,]+\s+\S+\s+\S+\s+.+?\s+([\d.,]+)\s+([\d.,]+)\s*$',
        right,
    )
    if not rm:
        rm = re.match(r'^(\d+)\s+(\d+)\s+.+?\s+([\d.,]+)\s+([\d.,]+)\s*$', right)
    if not rm:
        return None

    return {
        'lote': lm.group(1),
        'guia': lm.group(2),
        'cod_usuario': lm.group(3),
        'nome_usuario': lm.group(4).strip(),
        'cod_servico': lm.group(5),
        'desc_servico': lm.group(6).strip(),
        'guia_prest': lm.group(7),
        'data': _parse_data(data_str),
        'qtde': _parse_int(rm.group(1)),
        'valor_unit': _money_br(rm.group(3)),
        'valor_total': _money_br(rm.group(4)),
    }


def _parse_unimed_pdf_texto(pdf_bytes: bytes) -> tuple[dict[str, dict], set[tuple[str, str]]]:
    grupos: dict[str, dict] = {}
    servicos_unicos: set[tuple[str, str]] = set()

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ''
            for linha in texto.splitlines():
                parsed = _parse_linha_pdf_texto(linha)
                if not parsed:
                    continue
                obs = ''
                if parsed.get('guia_prest'):
                    obs = f"Guia prest.: {parsed['guia_prest']}"
                _adicionar_linha_grupo(
                    grupos,
                    servicos_unicos,
                    lote=parsed['lote'],
                    guia=parsed['guia'],
                    cod_usuario=parsed['cod_usuario'],
                    nome_usuario=parsed['nome_usuario'],
                    cod_servico=parsed['cod_servico'],
                    desc_servico=parsed['desc_servico'],
                    data=parsed['data'],
                    qtde=parsed['qtde'],
                    valor_unit=parsed['valor_unit'],
                    valor_total=parsed['valor_total'],
                    observacao=obs,
                )

    return grupos, servicos_unicos


def _extrair_tabelas_pdf(page) -> list[list[list[Any]]]:
    configs = [
        {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines', 'intersection_tolerance': 8},
        {'vertical_strategy': 'text', 'horizontal_strategy': 'text'},
        {'vertical_strategy': 'lines_strict', 'horizontal_strategy': 'lines_strict'},
        {},
    ]
    seen: list[list[list[Any]]] = []
    for cfg in configs:
        try:
            tables = page.extract_tables(cfg) or []
        except Exception:
            tables = []
        for table in tables:
            if table and len(table) >= 2:
                seen.append(table)
    return seen


def parse_unimed_pdf(pdf_bytes: bytes) -> tuple[dict[str, dict], set[tuple[str, str]]]:
    """
    Relatório UNIMED «Produção» em PDF.
    Ignora colunas: Plano, Tp. Grau, Participação %, Valor Ref.
    """
    grupos: dict[str, dict] = {}
    servicos_unicos: set[tuple[str, str]] = set()
    col_map: dict[str, int | None] | None = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in _extrair_tabelas_pdf(page):
                if not table or len(table) < 2:
                    continue

                header_idx = None
                for i, row in enumerate(table[:5]):
                    folded = _fold(' '.join(str(c or '') for c in row))
                    if 'lote' in folded and 'guia' in folded and 'serv' in folded:
                        header_idx = i
                        break

                if header_idx is None:
                    continue

                headers = [str(c or '') for c in table[header_idx]]
                candidate_map = _mapear_colunas_pdf(headers)
                if candidate_map.get('lote') is None or candidate_map.get('guia') is None:
                    continue

                if col_map is None:
                    col_map = candidate_map

                partial_grupos, partial_servicos = _parse_unimed_pdf_table(
                    table[header_idx + 1 :],
                    col_map,
                )
                grupos, servicos_unicos = _merge_grupos(
                    grupos, partial_grupos, servicos_unicos, partial_servicos
                )

    if not grupos:
        grupos, servicos_unicos = _parse_unimed_pdf_texto(pdf_bytes)

    if not grupos:
        raise ValueError(
            'Não foi possível ler o PDF UNIMED «Produção». '
            'Verifique se o arquivo tem texto selecionável (não é scan/foto) '
            'e se contém as colunas Lote, Guia e Cod.Serviço.'
        )

    return grupos, servicos_unicos


def persistir_unimed(
    grupos: dict[str, dict],
    servicos_unicos: set[tuple[str, str]],
    empresa_id: int,
) -> tuple[int, int, int]:
    """Cria serviços, faturamentos e itens. Retorna (servicos_criados, faturamentos, itens)."""
    servicos_criados = 0
    for cod, desc in servicos_unicos:
        if not ServicosMedicos.objects.filter(codigo=cod).exists():
            ServicosMedicos.objects.create(
                codigo=cod,
                servicos=desc,
                porte_anestesico=None,
            )
            servicos_criados += 1

    faturamentos_criados = 0
    itens_criados = 0

    for dados in grupos.values():
        faturamento = FaturamentoMedico.objects.create(
            empresa_id=empresa_id,
            lote=dados['lote'],
            guia=dados['guia'],
            carteirinha=dados['carteirinha'],
            nome=dados['nome'],
            data=dados['data'],
            convenio='UNIMED',
            codigo_relatorio=dados.get('cod_rel') or '',
            status='pendente',
        )

        for servico in dados['servicos']:
            ItemServico.objects.create(
                faturamento=faturamento,
                codigo_servico=servico['codigo'],
                servico=servico['descricao'],
                porte=servico.get('porte') or '',
                percentual=servico.get('percentual') or 0,
                qt=servico.get('qt') or 1,
                valor=servico.get('valor') or 0,
                total=servico.get('total') or 0,
            )
            itens_criados += 1

        faturamento.atualizar_total()
        faturamentos_criados += 1

    return servicos_criados, faturamentos_criados, itens_criados
