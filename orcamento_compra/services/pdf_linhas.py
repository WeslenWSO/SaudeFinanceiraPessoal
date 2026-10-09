"""Interpretação de linhas de produto/preço a partir do texto do PDF."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher


_RE_VALOR = re.compile(
    r'(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})'
)
_RE_LINHA_COM_VALOR = re.compile(
    r'^(?P<desc>.+?)\s+(?P<val>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*$'
)
_RE_QTD = re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(UN|UN\.|CX|PC|PCT|KG|ML|LT)\b', re.I)

_IGNORE = re.compile(
    r'^(total|subtotal|desconto|frete|valor|pagina|página|cnpj|cpf|'
    r'orcamento|orçamento|proposta|data|validade|telefone|email|e-mail|'
    r'endereco|endereço|cep|bairro|cidade|uf|inscri)',
    re.I,
)


def _normalizar(txt: str) -> str:
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', txt.lower().strip())


def _parse_valor_br(texto: str) -> Decimal | None:
    texto = (texto or '').strip()
    if not texto:
        return None
    try:
        return Decimal(texto.replace('.', '').replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def extrair_linhas_orcamento_pdf(texto: str) -> list[dict]:
    """
    Retorna lista de dicts: idx, descricao, quantidade (str|None), preco_unit, preco_total (str decimal).
    """
    if not (texto or '').strip():
        return []

    linhas_raw = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    saida: list[dict] = []
    idx = 0

    for ln in linhas_raw:
        if len(ln) < 4:
            continue
        if _IGNORE.match(ln):
            continue
        if not _RE_VALOR.search(ln):
            continue

        m = _RE_LINHA_COM_VALOR.match(ln)
        if m:
            desc = m.group('desc').strip(' .-–—\t')
            val = _parse_valor_br(m.group('val'))
        else:
            vals = _RE_VALOR.findall(ln)
            if not vals:
                continue
            val = _parse_valor_br(vals[-1])
            desc = ln[: ln.rfind(vals[-1])].strip(' .-–—\t')

        if not desc or len(desc) < 3:
            continue
        if val is None or val <= 0:
            continue

        qtd = None
        mq = _RE_QTD.search(desc)
        if mq:
            qtd = mq.group(1).replace(',', '.')

        saida.append({
            'idx': idx,
            'descricao': desc[:300],
            'quantidade': qtd,
            'preco_unit': None,
            'preco_total': str(val.quantize(Decimal('0.01'))),
            'item_id': None,
        })
        idx += 1

    return saida


def sugerir_item_id(descricao_pdf: str, itens: list) -> int | None:
    """Sugere item do orçamento pelo texto (similaridade)."""
    alvo = _normalizar(descricao_pdf)
    if not alvo:
        return None
    melhor_id = None
    melhor_score = 0.0
    for item in itens:
        cand = _normalizar(item.descricao)
        if not cand:
            continue
        score = SequenceMatcher(None, alvo, cand).ratio()
        if alvo in cand or cand in alvo:
            score = max(score, 0.85)
        tokens_a = set(alvo.split())
        tokens_b = set(cand.split())
        if len(tokens_a & tokens_b) >= 2:
            score = max(score, 0.75)
        if score > melhor_score:
            melhor_score = score
            melhor_id = item.pk
    if melhor_score >= 0.45:
        return melhor_id
    return None


def aplicar_sugestoes(linhas: list[dict], itens: list) -> list[dict]:
    usados: set[int] = set()
    for linha in linhas:
        if linha.get('item_id'):
            try:
                usados.add(int(linha['item_id']))
            except (TypeError, ValueError):
                pass
    for linha in linhas:
        if linha.get('item_id'):
            continue
        sug = sugerir_item_id(linha.get('descricao') or '', itens)
        if sug and sug not in usados:
            linha['item_id'] = sug
            usados.add(sug)
    return linhas
