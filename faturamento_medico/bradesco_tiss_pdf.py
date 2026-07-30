"""
Parser do Demonstrativo de Pagamento TISS — Bradesco Saúde (PDF imagem ou texto).

Extrai linhas de resumo (protocolo/lote/valores) por data de pagamento.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from emprestimos.bradesco_pdf import extrair_texto_bradesco
from emprestimos.sicoob_pdf import _dec, _parse_data


def _normalizar_texto(texto: str) -> str:
    t = (texto or '').replace('\r', '\n')
    t = re.sub(r'(\d)\s+,\s*(\d)', r'\1,\2', t)
    t = re.sub(r'[ \t]+', ' ', t)
    return t


def _campo(texto: str, *padroes: str) -> str | None:
    for p in padroes:
        m = re.search(p, texto, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def _parse_competencia(texto: str | None) -> str | None:
    """Retorna MM/YYYY a partir de '01/2026', '01-2026' ou 'competencia 01-2026'."""
    if not texto:
        return None
    m = re.search(r'(\d{1,2})[/-](\d{4})', texto.strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}/{m.group(2)}"


def _parse_debitos(bloco: str) -> dict[str, Decimal]:
    debitos = {
        'irrf': Decimal('0'),
        'iss': Decimal('0'),
        'inss': Decimal('0'),
        'pis': Decimal('0'),
        'cofins': Decimal('0'),
        'csll': Decimal('0'),
        'descontos': Decimal('0'),
    }
    mapa = [
        (r'D[eé]bito\s*1\b.*?([\d.,]+)\s*$', 'irrf'),
        (r'D[eé]bito\s*2\b.*?([\d.,]+)\s*$', 'iss'),
        (r'D[eé]bito\s*3\b.*?([\d.,]+)\s*$', 'inss'),
        (r'D[eé]bito\s*4\b.*?([\d.,]+)\s*$', 'pis'),
        (r'D[eé]bito\s*5\b.*?([\d.,]+)\s*$', 'cofins'),
        (r'D[eé]bito\s*6\b.*?([\d.,]+)\s*$', 'csll'),
        (r'D[eé]bito\s*7\b.*?([\d.,]+)\s*$', 'descontos'),
    ]
    for linha in bloco.splitlines():
        ln = linha.strip()
        if not ln.upper().startswith('D') and 'bito' not in ln.lower():
            continue
        for pat, chave in mapa:
            m = re.search(pat, ln, flags=re.IGNORECASE)
            if m:
                debitos[chave] = _dec(m.group(1))
                break
    return debitos


def _parse_blocos_pagamento(texto: str) -> list[str]:
    marcadores = list(
        re.finditer(
            r'Dados do Pagamento\s*(?:\r?\n)+\s*Data do pagamento\s*(\d{2}/\d{2}/\d{4})',
            texto,
            flags=re.IGNORECASE,
        )
    )
    if not marcadores:
        return [texto]
    blocos: list[str] = []
    for i, m in enumerate(marcadores):
        ini = m.start()
        fim = marcadores[i + 1].start() if i + 1 < len(marcadores) else len(texto)
        blocos.append(texto[ini:fim])
    return blocos


def _parse_linhas_resumo(bloco: str) -> list[dict[str, Any]]:
    # Limita à seção "Dados do Resumo" (evita repetição de rodapé entre páginas)
    cortes = re.split(r'Valores Brutos por Data de Pagamento', bloco, maxsplit=1, flags=re.IGNORECASE)
    trecho = cortes[0]
    linhas: list[dict[str, Any]] = []
    padrao = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+'
        r'(\d{10,})\s+'
        r'(\d{4,})\s+'
        r'([\d.,]+)\s+'
        r'([\d.,\s]+)\s+'
        r'([\d.,]+)\s+'
        r'([\d.,]+)',
        flags=re.MULTILINE,
    )
    for m in padrao.finditer(trecho):
        data_protocolo = _parse_data(m.group(1))
        if not data_protocolo:
            continue
        linhas.append({
            'data_protocolo': data_protocolo,
            'protocolo': m.group(2),
            'lote': m.group(3),
            'valor_informado': _dec(m.group(4)),
            'valor_processado': _dec(re.sub(r'\s+', '', m.group(5))),
            'valor_liberado': _dec(m.group(6)),
            'valor_glosa': _dec(m.group(7)),
        })
    # Remove duplicatas exatas (OCR repete blocos entre páginas)
    vistos: set[tuple] = set()
    unicos: list[dict[str, Any]] = []
    for row in linhas:
        chave = (
            row['data_protocolo'],
            row['protocolo'],
            row['lote'],
            row['valor_informado'],
            row['valor_liberado'],
        )
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(row)
    return unicos


def _parse_qt_guias(bloco: str) -> int | None:
    m = re.search(r'(\d+)\s*Guias?\s+do\s+Lote', bloco, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    # OCR: "EB Guias" → 8
    m2 = re.search(r'([EeBb8]{1,2})\s*Guias?\s+do\s+Lote', bloco, flags=re.IGNORECASE)
    if m2:
        raw = m2.group(1).upper()
        if raw.isdigit():
            return int(raw)
        if raw in ('E', 'EB', 'B'):
            return 8
    return None


def _parse_valor_final(bloco: str) -> Decimal | None:
    m = re.search(
        r'Valor Final(?:\s+a|\s+à)?\s+Receber por Data de Pagamento\s*\(R\$\)\s*([\d.,]+)',
        bloco,
        flags=re.IGNORECASE,
    )
    if m:
        return _dec(m.group(1))
    return None


def parse_extrato_pagamento_bradesco(
    file_obj,
    *,
    competencia: str | None = None,
    nome_arquivo: str | None = None,
) -> dict[str, Any]:
    """
    Lê PDF TISS Bradesco Saúde e devolve cabeçalho + linhas para importação.
    """
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    texto_bruto = extrair_texto_bradesco(file_obj)
    texto = _normalizar_texto(texto_bruto)

    if 'DEMONSTRATIVO DE PAGAMENTO' not in texto.upper() and 'DEMONSTRATIVOSTISS' not in texto.upper().replace(' ', ''):
        raise ValueError(
            'PDF não reconhecido como Demonstrativo de Pagamento TISS Bradesco Saúde.'
        )

    competencia_final = (
        _parse_competencia(competencia)
        or _parse_competencia(nome_arquivo)
    )

    cabecalho = {
        'convenio': 'BRADESCO SAUDE',
        'numero_demonstrativo': _campo(
            texto,
            r'Numero do Demonstrativo\s*(\d+)',
            r'N[uú]mero do Demonstrativo\s*(\d+)',
        ),
        'data_emissao': _parse_data(_campo(
            texto,
            r'Data Emiss[aã]?[oõ] Demonstrativo\s*(\d{2}/\d{2}/\d{4})',
        )),
        'codigo_prestador': _campo(
            texto,
            r'C[oó]digo na Operadora\s*(\d+)',
            r'C.digo na Operadora\s*(\d+)',
        ),
        'nome_prestador': _campo(
            texto,
            r'Nome do Contratado\s*(.+?)(?:\n|C[oó]digo CNES)',
        ),
        'competencia': competencia_final,
    }

    linhas: list[dict[str, Any]] = []
    for bloco in _parse_blocos_pagamento(texto):
        data_pagamento = _parse_data(_campo(bloco, r'Data do pagamento\s*(\d{2}/\d{2}/\d{4})'))
        if not data_pagamento:
            continue
        debitos = _parse_debitos(bloco)
        retencoes = sum(debitos.values())
        valor_final = _parse_valor_final(bloco)
        qt_guias = _parse_qt_guias(bloco)

        for row in _parse_linhas_resumo(bloco):
            valor_liberado = row['valor_liberado']
            liquido = valor_final
            if liquido is None and valor_liberado:
                liquido = (valor_liberado - retencoes).quantize(Decimal('0.01'))
            chave = (
                row['protocolo'],
                row['lote'],
                row['valor_informado'],
                valor_liberado,
                data_pagamento,
            )
            if chave in {
                (l['protocolo'], l['lote'], l['valor'], l['valor_liberado'], l.get('data_previsao'))
                for l in linhas
            }:
                continue
            linhas.append({
                **cabecalho,
                'competencia': competencia_final or '',
                'data_lote': row['data_protocolo'],
                'lote': row['lote'],
                'protocolo': row['protocolo'],
                'qt_guias': qt_guias,
                'valor': row['valor_informado'],
                'valor_processado': row['valor_processado'],
                'valor_glosado': row['valor_glosa'],
                'valor_liberado': valor_liberado,
                'retencoes': retencoes,
                'liquido': liquido or Decimal('0'),
                'observacao': '',
                'nota': '',
                'valor_nota': None,
                'data_previsao': data_pagamento,
            })

    if not linhas:
        raise ValueError('Nenhuma linha de protocolo/lote encontrada no PDF.')

    return {
        'cabecalho': cabecalho,
        'linhas': linhas,
        'texto_ocr': texto_bruto[:4000],
    }


def parece_bradesco_tiss(texto: str) -> bool:
    u = (texto or '').upper()
    return (
        'DEMONSTRATIVO DE PAGAMENTO' in u
        or 'PCBS-DEMONSTRATIVOSTISS' in u.replace(' ', '')
        or ('BRADESCO' in u and 'VALOR DA GLOSA' in u)
    )
