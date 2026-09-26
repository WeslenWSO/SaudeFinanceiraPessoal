"""Busca imagem de produto na internet (Google CSE, DuckDuckGo, Openverse) com cache."""
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
_TIMEOUT = 10
_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def _simplificar_nome_nf(nome: str) -> str:
    """Nome curto para busca de imagem (remove ruído típico de item de NF)."""
    n = re.sub(r'\s+', ' ', (nome or '').strip())
    n = re.sub(r'\s*-\s*GENERICO\s*', ' ', n, flags=re.I)
    n = re.sub(r'\([^)]*\)', '', n)
    n = re.sub(
        r'\s+(FRASC|AMP|SOL|INJ|ORAL|INALAT|COMPRIM|CAPS|GOTAS|MIL|UNID).*$',
        '',
        n,
        flags=re.I,
    )
    return n.strip()[:100]


def _limpar_query(nome: str, codigo: str = '') -> list[str]:
    nome = (nome or '').strip()
    codigo = (codigo or '').strip()
    queries: list[str] = []
    simples = _simplificar_nome_nf(nome)
    if simples:
        queries.append(simples)
    if nome:
        queries.append(nome[:140])
    if codigo and simples:
        queries.append(f'{codigo} {simples}'[:140])
    elif codigo and nome:
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
    termo = termo_busca_foto(nome, codigo)
    if not termo:
        return 'https://www.google.com/search?tbm=isch'
    return f'https://www.google.com/search?tbm=isch&q={quote_plus(termo)}'


def _google_cse_configurado() -> tuple[str, str]:
    key = getattr(settings, 'GOOGLE_CSE_API_KEY', '') or ''
    cx = getattr(settings, 'GOOGLE_CSE_CX', '') or ''
    return key.strip(), cx.strip()


def _wikipedia_user_agent() -> str:
    return getattr(
        settings,
        'WIKIPEDIA_USER_AGENT',
        'SaudeFinanceiraPessoal/1.0 (notafiscal-comercio; contacto via app)',
    )


def _wikipedia_thumb_por_titulo(lang: str, title: str, headers: dict) -> str | None:
    try:
        resp = requests.get(
            f'https://{lang}.wikipedia.org/w/api.php',
            params={
                'action': 'query',
                'titles': title,
                'prop': 'pageimages',
                'piprop': 'thumbnail',
                'pithumbsize': 200,
                'format': 'json',
            },
            headers=headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        pages = resp.json().get('query', {}).get('pages') or {}
    except (requests.RequestException, ValueError):
        return None
    for page in pages.values():
        if page.get('missing'):
            continue
        thumb = (page.get('thumbnail') or {}).get('source')
        if thumb and str(thumb).startswith('http'):
            return str(thumb)
    return None


def _buscar_wikipedia_thumb(query: str) -> str | None:
    headers = {'User-Agent': _wikipedia_user_agent()}
    palavras = [p for p in re.split(r'\s+', query.strip()) if p]
    termos: list[str] = []
    if palavras:
        termos.append(palavras[0])
    if query and query not in termos:
        termos.append(query)

    for lang in ('en', 'pt'):
        termo = termos[0]
        try:
            resp = requests.get(
                f'https://{lang}.wikipedia.org/w/api.php',
                params={
                    'action': 'opensearch',
                    'search': termo,
                    'limit': 5,
                    'namespace': 0,
                    'format': 'json',
                },
                headers=headers,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            titles = resp.json()[1] or []
        except (requests.RequestException, ValueError, IndexError) as exc:
            logger.warning('Wikipedia opensearch (%s) falhou: %s', lang, exc)
            continue

        termo_low = termo.lower()
        for title in titles:
            titulo_low = title.lower()
            if termo_low not in titulo_low and not (
                palavras and palavras[0].lower() in titulo_low
            ):
                continue
            thumb = _wikipedia_thumb_por_titulo(lang, title, headers)
            if thumb:
                return thumb
    return None


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
                'num': 5,
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


def _vqd_duckduckgo(query: str) -> str | None:
    try:
        resp = requests.get(
            'https://duckduckgo.com/',
            params={'q': query, 'iax': 'images', 'ia': 'images'},
            headers={'User-Agent': _UA, 'Accept': 'text/html'},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.text
    except requests.RequestException as exc:
        logger.warning('DDG vqd falhou: %s', exc)
        return None

    for pattern in (
        r'vqd="([\d-]+)"',
        r"vqd='([\d-]+)'",
        r'vqd=([\d-]+)&',
        r'"vqd":"([\d-]+)"',
    ):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def _buscar_duckduckgo_imagens(query: str) -> str | None:
    """Busca de imagens na web (sem chave de API), similar ao Google Imagens."""
    vqd = _vqd_duckduckgo(query)
    if not vqd:
        return None
    try:
        resp = requests.get(
            'https://duckduckgo.com/i.js',
            params={
                'l': 'wt-wt',
                'o': 'json',
                'q': query,
                'vqd': vqd,
                'f': ',,,',
                'p': '1',
            },
            headers={
                'User-Agent': _UA,
                'Referer': 'https://duckduckgo.com/',
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('DDG imagens falhou (%s): %s', query[:40], exc)
        return None

    for hit in (data.get('results') or [])[:8]:
        url = hit.get('thumbnail') or hit.get('image')
        if url and str(url).startswith('http'):
            return str(url)
    return None


def _buscar_openverse(query: str) -> str | None:
    try:
        resp = requests.get(
            _OPENVERSE,
            params={'q': query, 'page_size': 5},
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
    queries = _limpar_query(nome, codigo)
    for query in queries:
        url = _buscar_google_cse(query)
        if url:
            return url, 'google'

    principal = termo_busca_foto(nome, codigo)
    if principal:
        url = _buscar_wikipedia_thumb(principal)
        if url:
            return url, 'wikipedia'

    for query in queries:
        url = _buscar_duckduckgo_imagens(query)
        if url:
            return url, 'duckduckgo'
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
            'fonte': fonte or 'duckduckgo',
            'atualizado_em': timezone.now(),
        },
    )
    return obj


_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56">'
    b'<rect fill="#f1f3f5" width="56" height="56" rx="4"/>'
    b'<text x="28" y="32" text-anchor="middle" fill="#ced4da" font-family="sans-serif" font-size="11">?</text>'
    b'</svg>'
)


def baixar_bytes_imagem(url: str) -> tuple[bytes | None, str]:
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': _UA, 'Accept': 'image/*,*/*;q=0.8'},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        ctype = (resp.headers.get('Content-Type') or 'image/jpeg').split(';')[0].strip()
        if not ctype.startswith('image/'):
            ctype = 'image/jpeg'
        return resp.content, ctype
    except requests.RequestException as exc:
        logger.warning('Download imagem falhou: %s', exc)
        return None, ''


def placeholder_foto_svg() -> bytes:
    return _PLACEHOLDER_SVG


def mapa_fotos_por_codigo(empresa_id: int, codigos: list[str]) -> dict[str, str]:
    if not codigos:
        return {}
    qs = ProdutoComercioFoto.objects.filter(
        empresa_id=empresa_id,
        codigo_produto__in=codigos,
    )
    return {row.codigo_produto: row.url_imagem for row in qs}
