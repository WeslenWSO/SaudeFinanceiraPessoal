"""Busca imagem de produto (Google Imagens / Openverse) com cache em banco."""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

import requests
from django.conf import settings
from django.utils import timezone

from notafiscalentrada.models import ProdutoComercioFoto

logger = logging.getLogger(__name__)

_OPENVERSE = 'https://api.openverse.org/v1/images/'
_GOOGLE_CSE = 'https://www.googleapis.com/customsearch/v1'
_TIMEOUT = 12


def _limpar_query(nome: str, codigo: str = '') -> list[str]:
    nome = (nome or '').strip()
    codigo = (codigo or '').strip()
    queries: list[str] = []
    if nome:
        queries.append(nome[:140])
    if codigo and nome:
        queries.append(f'{codigo} {nome}'[:140])
    elif codigo:
        queries.append(codigo[:140])
    out: list[str] = []
    for q in queries:
        q2 = re.sub(r'\s+', ' ', q).strip()
        if q2 and q2 not in out:
            out.append(q2)
    return out


def termo_busca_foto(nome: str, codigo: str = '') -> str:
    queries = _limpar_query(nome, codigo)
    if queries:
        return queries[0]
    return (codigo or nome or '').strip()


def url_google_imagens(nome: str, codigo: str = '') -> str:
    """Link para abrir a busca de imagens no Google (nome/código do produto)."""
    termo = termo_busca_foto(nome, codigo)
    if not termo:
        return 'https://www.google.com/search?tbm=isch'
    return f'https://www.google.com/search?tbm=isch&q={quote_plus(termo)}'


def _google_cse_configurado() -> tuple[str, str]:
    key = getattr(settings, 'GOOGLE_CSE_API_KEY', '') or ''
    cx = getattr(settings, 'GOOGLE_CSE_CX', '') or ''
    return key.strip(), cx.strip()


def _buscar_google_cse(query: str) -> str | None:
    api_key, cx = _google_cse_configurado()
    if not api_key or not cx:
        return None
    try:
        resp = requests.get(
            _GOOGLE_CSE,
            params={
                'key': api_key,
                'cx': cx,
                'q': query,
                'searchType': 'image',
                'num': 3,
                'safe': 'active',
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get('items') or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Google CSE falhou (%s): %s', query[:40], exc)
        return None

    for hit in items:
        link = hit.get('link')
        if link and str(link).startswith('http'):
            return str(link)
    return None


def _buscar_openverse(query: str) -> str | None:
    try:
        resp = requests.get(
            _OPENVERSE,
            params={
                'q': query,
                'page_size': 5,
            },
            timeout=_TIMEOUT,
            headers={'Accept': 'application/json'},
        )
        resp.raise_for_status()
        results = resp.json().get('results') or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Openverse falhou (%s): %s', query[:40], exc)
        return None

    for hit in results:
        url = hit.get('thumbnail') or hit.get('url')
        if url and str(url).startswith('http'):
            return str(url)
    return None


def buscar_url_imagem_internet(nome: str, codigo: str = '') -> tuple[str | None, str]:
    for query in _limpar_query(nome, codigo):
        url = _buscar_google_cse(query)
        if url:
            return url, 'google'
        url = _buscar_openverse(query)
        if url:
            return url, 'openverse'
    return None, ''


def obter_foto_produto(
    empresa_id: int,
    codigo_produto: str,
    nome_produto: str = '',
    *,
    forcar_busca: bool = False,
) -> ProdutoComercioFoto | None:
    codigo_produto = (codigo_produto or '').strip()
    if not codigo_produto:
        return None

    existente = ProdutoComercioFoto.objects.filter(
        empresa_id=empresa_id,
        codigo_produto=codigo_produto,
    ).first()
    if existente and not forcar_busca:
        return existente

    url, fonte = buscar_url_imagem_internet(nome_produto, codigo_produto)
    if not url:
        return existente

    obj, _ = ProdutoComercioFoto.objects.update_or_create(
        empresa_id=empresa_id,
        codigo_produto=codigo_produto,
        defaults={
            'nome_produto': (nome_produto or '')[:200],
            'url_imagem': url[:600],
            'fonte': fonte or 'google',
            'atualizado_em': timezone.now(),
        },
    )
    return obj


def mapa_fotos_por_codigo(empresa_id: int, codigos: list[str]) -> dict[str, str]:
    if not codigos:
        return {}
    qs = ProdutoComercioFoto.objects.filter(
        empresa_id=empresa_id,
        codigo_produto__in=codigos,
    )
    return {row.codigo_produto: row.url_imagem for row in qs}
