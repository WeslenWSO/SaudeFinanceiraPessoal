"""Catálogos fiscais NFS-e (Padrão Nacional) para selects com busca na UI."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DADOS_DIR = Path(__file__).resolve().parent / 'dados'

NATUREZA_OPERACAO_PADRAO = [
    {'codigo': '1', 'label': 'Operação tributável', 'descricao': 'Operação tributável'},
    {'codigo': '2', 'label': 'Imunidade', 'descricao': 'Imunidade'},
    {'codigo': '3', 'label': 'Exportação de serviço', 'descricao': 'Exportação de serviço'},
    {'codigo': '4', 'label': 'Não Incidência', 'descricao': 'Não Incidência'},
]


def _normalizar_lei_116(valor: str) -> str:
    digits = re.sub(r'\D', '', valor or '')
    return digits[:4]


def _normalizar_nbs(valor: str) -> str:
    return re.sub(r'\s', '', (valor or '').strip())


@lru_cache(maxsize=1)
def _carregar(nome: str) -> list[dict]:
    path = DADOS_DIR / nome
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return []


def naturezas_operacao() -> list[dict]:
    dados = _carregar('natureza_operacao.json')
    return dados or NATUREZA_OPERACAO_PADRAO


def listar_c_class_trib(*, q: str = '', limite: int = 30) -> list[dict]:
    return _filtrar(_carregar('c_class_trib.json'), q, limite, ('codigo', 'descricao', 'label'))


def listar_indicador_operacao(*, q: str = '', lei_116: str = '', limite: int = 30) -> list[dict]:
    todos = _carregar('indicador_operacao.json')
    if lei_116:
        item = _normalizar_lei_116(lei_116)
        correl = _carregar('correlacao_lc116_ibscbs.json')
        codigos = {c['indicador_operacao'] for c in correl if c.get('item_lc116') == item}
        filtrados = [i for i in todos if i.get('codigo') in codigos]
        if filtrados:
            sugeridos = _filtrar(filtrados, q, limite, ('codigo', 'descricao', 'label'))
            if sugeridos:
                return sugeridos
    return _filtrar(todos, q, limite, ('codigo', 'descricao', 'label'))


def listar_nbs(*, q: str = '', lei_116: str = '', limite: int = 30) -> list[dict]:
    todos = _carregar('nbs.json')
    if lei_116:
        item = _normalizar_lei_116(lei_116)
        correl = _carregar('correlacao_lc116_ibscbs.json')
        codigos = {_normalizar_nbs(c['codigo_nbs']) for c in correl if c.get('item_lc116') == item}
        filtrados = [n for n in todos if _normalizar_nbs(n.get('codigo', '')) in codigos]
        if filtrados:
            sugeridos = _filtrar(filtrados, q, limite, ('codigo', 'label'))
            if sugeridos:
                return sugeridos
    return _filtrar(todos, q, limite, ('codigo', 'label'))


def listar_codigo_servico_municipal(*, q: str = '', lei_116: str = '', limite: int = 30) -> list[dict]:
    todos = _carregar('codigo_servico_lc116.json')
    if lei_116:
        item = _normalizar_lei_116(lei_116)
        filtrados = [c for c in todos if str(c.get('item_lc116', '')).startswith(item[:4]) or item in str(c.get('item_lc116', ''))]
        if filtrados:
            sugeridos = _filtrar(filtrados, q, limite, ('codigo', 'label', 'item_lc116'))
            if sugeridos:
                return sugeridos
    return _filtrar(todos, q, limite, ('codigo', 'label', 'item_lc116'))


def sugestoes_por_lei_116(lei_116: str) -> dict:
    """Combinações mais usadas para o item LC 116 (estilo Conta Azul)."""
    item = _normalizar_lei_116(lei_116)
    if not item:
        return {}
    correl = _carregar('correlacao_lc116_ibscbs.json')
    linhas = [c for c in correl if c.get('item_lc116') == item]
    if not linhas:
        return {}

    nbs_counter: dict[str, int] = {}
    ind_counter: dict[str, int] = {}
    trib_counter: dict[str, int] = {}
    for linha in linhas:
        nbs_counter[linha['codigo_nbs']] = nbs_counter.get(linha['codigo_nbs'], 0) + 1
        ind_counter[linha['indicador_operacao']] = ind_counter.get(linha['indicador_operacao'], 0) + 1
        trib_counter[linha['c_class_trib']] = trib_counter.get(linha['c_class_trib'], 0) + 1

    def _top(counter: dict[str, int]) -> str:
        return max(counter, key=counter.get) if counter else ''

    return {
        'codigo_nbs': _top(nbs_counter),
        'indicador_operacao': _top(ind_counter),
        'c_class_trib': _top(trib_counter),
    }


def _filtrar(itens: list[dict], q: str, limite: int, campos: tuple[str, ...]) -> list[dict]:
    q_norm = (q or '').strip().lower()
    if not q_norm:
        return itens[:limite]
    resultado = []
    for item in itens:
        texto = ' '.join(str(item.get(c) or '') for c in campos).lower()
        if q_norm in texto:
            resultado.append(item)
        if len(resultado) >= limite:
            break
    return resultado
