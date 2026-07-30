"""Parser de fatura de cartão de crédito Sicredi (PDF)."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .categorias import resolver_categoria

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

_MESES = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
}


def _fold(s: str) -> str:
    if not s:
        return ''
    d = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in d if unicodedata.category(c) != 'Mn').lower()


def _parse_moeda(txt: str) -> Decimal:
    s = (txt or '').replace('R$', '').replace(' ', '').strip()
    if not s:
        return Decimal('0')
    s = s.replace('.', '').replace(',', '.')
    try:
        return Decimal(s).quantize(Decimal('0.01'))
    except InvalidOperation:
        return Decimal('0')


def _parse_data(txt: str, ano_ref: int | None = None) -> date | None:
    if not txt:
        return None
    txt = txt.strip().lower()
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', txt)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r'(\d{2})/(\d{2,3})', txt)
    if m:
        dia = int(m.group(1))
        mes_txt = m.group(2)
        if mes_txt.isdigit():
            return date(ano_ref or datetime.now().year, int(mes_txt), dia)
        mes = _MESES.get(mes_txt[:3])
        if mes:
            ano = ano_ref or datetime.now().year
            return date(ano, mes, dia)
    m = re.match(r'(\d{2})/([a-z]{3})', txt)
    if m:
        mes = _MESES.get(m.group(2)[:3])
        if mes:
            ano = ano_ref or datetime.now().year
            return date(ano, mes, int(m.group(1)))
    return None


def _inferir_ano(texto: str) -> int | None:
    m = re.search(r'Vencimento\s+\d{2}/\d{2}/(\d{4})', texto, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'Fechamento da pr[oó]xima fatura\s+\d{2}/\d{2}/(\d{4})', texto, re.I)
    if m:
        return int(m.group(1))
    return None


def _classificar_linha(meio: str) -> str:
    m = _fold(meio)
    if 'pagamento' in m:
        return 'pagamento'
    if m.startswith('iof'):
        return 'iof'
    return 'compra'


def _hash_icone(im: dict) -> str:
    stream = im.get('stream')
    if stream is None:
        return ''
    return hashlib.md5(stream.get_data()).hexdigest()[:12]


def _icone_na_linha(icons: list[dict], y: float, tol: float = 5.0) -> dict | None:
    for im in icons:
        if abs(im['top'] - y) <= tol:
            return im
    return None


def _agrupar_palavras_em_linhas(words: list[dict]) -> list[list[dict]]:
    if not words:
        return []
    ordenadas = sorted(words, key=lambda w: (round(w['top'], 1), w['x0']))
    linhas: list[list[dict]] = []
    linha_atual: list[dict] = []
    y_ref = None
    for w in ordenadas:
        y = round(w['top'], 1)
        if y_ref is None or abs(y - y_ref) <= 2:
            linha_atual.append(w)
            y_ref = y if y_ref is None else (y_ref + y) / 2
        else:
            if linha_atual:
                linhas.append(sorted(linha_atual, key=lambda x: x['x0']))
            linha_atual = [w]
            y_ref = y
    if linha_atual:
        linhas.append(sorted(linha_atual, key=lambda x: x['x0']))
    return linhas


def _extrair_mapa_categorias(pdf, ano_ref: int | None) -> dict[tuple, str]:
    mapa: dict[tuple, str] = {}
    for page in pdf.pages:
        words = page.extract_words()
        icons = [
            im for im in page.images
            if 12 <= im['width'] <= 14 and 210 <= im['x0'] <= 230
        ]
        for linha_words in _agrupar_palavras_em_linhas(words):
            linha = ' '.join(w['text'] for w in linha_words)
            item = _parse_linha_transacao(linha, ano_ref)
            if not item or item['tipo'] != 'compra':
                continue
            icone = _icone_na_linha(icons, linha_words[0]['top'])
            icone_hash = _hash_icone(icone) if icone else ''
            cat = resolver_categoria(
                item['descricao'],
                tipo_compra=item.get('tipo_compra', ''),
                icone_hash=icone_hash,
            )
            if cat:
                chave = (item['data'], item['hora'], item['valor'])
                mapa[chave] = cat
    return mapa


def _parse_linha_transacao(linha: str, ano_ref: int | None) -> dict[str, Any] | None:
    linha = ' '.join(linha.split())
    if not linha or linha.startswith('Data e hora') or linha.startswith('Total cart'):
        return None
    if linha.startswith('(') or 'Transac' in linha[:20]:
        return None

    m_val = re.search(r'(-?\s*R\$\s*[\d.,]+)\s*$', linha)
    if not m_val:
        return None
    valor = _parse_moeda(m_val.group(1))
    corpo = linha[: m_val.start()].strip()

    m_dt = re.match(
        r'^(\d{2}/(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|\d{2}))\s+'
        r'(\d{2}:\d{2})\s+(.+)$',
        corpo,
        re.I,
    )
    if not m_dt:
        return None

    data_txt, hora, resto = m_dt.group(1), m_dt.group(2), m_dt.group(3).strip()
    data = _parse_data(data_txt, ano_ref)
    if not data:
        return None

    parcela_txt = ''
    m_parc = re.search(r'\b(\d{2}/\d{2})\s*$', resto)
    if m_parc:
        parcela_txt = m_parc.group(1)
        resto = resto[: m_parc.start()].strip()

    cidade = ''
    tipo_compra = ''
    descricao = resto
    m_cidade = re.match(r'^(.+?)\s+(Online|Presencial)\s+(.+)$', resto, re.I)
    if m_cidade:
        cidade = m_cidade.group(1).strip()
        tipo_compra = m_cidade.group(2).strip()
        descricao = m_cidade.group(3).strip()
    elif resto.lower().startswith('pagamento'):
        descricao = resto
    elif resto.lower().startswith('iof'):
        descricao = resto

    tipo = _classificar_linha(resto)
    return {
        'data': data,
        'hora': hora,
        'cidade': cidade,
        'tipo_compra': tipo_compra,
        'descricao': descricao,
        'parcela': parcela_txt,
        'valor': valor,
        'tipo': tipo,
    }


def parse_fatura_sicredi_pdf(arquivo) -> dict[str, Any]:
    if pdfplumber is None:
        raise RuntimeError('Biblioteca pdfplumber não instalada.')

    texto_completo = []
    mapa_categorias: dict[tuple, str] = {}
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto_completo.append(page.extract_text() or '')
        blob = '\n'.join(texto_completo)
        ano_ref = _inferir_ano(blob)
        mapa_categorias = _extrair_mapa_categorias(pdf, ano_ref)

    titular = ''
    m_tit = re.search(r'^([A-Za-z0-9\s]+)\s+Limite total', blob, re.M)
    if m_tit:
        titular = m_tit.group(1).strip()

    bandeira = 'Visa' if 'visa' in _fold(blob) else ''
    final_cartao = ''
    m_final = re.search(r'final\s+(\d{4})', blob, re.I)
    if m_final:
        final_cartao = m_final.group(1)

    vencimento = None
    m_venc = re.search(
        r'Vencimento\s+(\d{2}/(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|\d{2})(?:/\d{4})?)',
        blob,
        re.I,
    )
    if m_venc:
        venc_txt = m_venc.group(1)
        m_ano = re.search(r'Vencimento\s+\d{2}/\d{2}/(\d{4})', blob, re.I)
        if m_ano and '/' not in venc_txt[3:]:
            venc_txt = f'{venc_txt}/{m_ano.group(1)}'
        vencimento = _parse_data(venc_txt, ano_ref)

    total_fatura = Decimal('0')
    m_tot = re.search(r'Total desta Fatura\s+([\d.,]+)', blob, re.I)
    if m_tot:
        total_fatura = _parse_moeda(m_tot.group(1))
    if total_fatura <= 0:
        m_tot2 = re.search(r'Total fatura de\s+\w+\s+R\$\s*([\d.,]+)', blob, re.I)
        if m_tot2:
            total_fatura = _parse_moeda(m_tot2.group(1))

    referencia = ''
    m_ref = re.search(r'Total fatura de\s+(\w+)', blob, re.I)
    if m_ref:
        referencia = m_ref.group(1).capitalize()

    itens: list[dict[str, Any]] = []
    cartao_atual = ''
    final_atual = ''

    for linha in blob.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m_cart = re.search(
            r'Cart[aã]o(?: portador virtual)?\s+(.+?)\s+\(final\s+(\d{4})\)',
            linha,
            re.I,
        )
        if m_cart:
            cartao_atual = m_cart.group(1).strip()
            final_atual = m_cart.group(2)
            continue

        item = _parse_linha_transacao(linha, ano_ref)
        if not item:
            continue
        item['cartao_portador'] = cartao_atual
        item['cartao_final'] = final_atual
        if item['tipo'] == 'compra':
            chave = (item['data'], item['hora'], item['valor'])
            item['categoria'] = mapa_categorias.get(chave) or resolver_categoria(
                item['descricao'],
                tipo_compra=item.get('tipo_compra', ''),
            )
        itens.append(item)

    return {
        'banco': 'Sicredi',
        'titular': titular,
        'bandeira': bandeira,
        'cartao_final': final_cartao,
        'referencia_mes': referencia,
        'vencimento': vencimento,
        'total_fatura': total_fatura,
        'itens': itens,
        'qtd_itens': len(itens),
    }
