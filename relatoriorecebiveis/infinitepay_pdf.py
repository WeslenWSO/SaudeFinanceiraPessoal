"""
Extração de linhas do relatório PDF «Recebimentos» Infinite Pay (Conta Web / maquininha).

Tenta extrair tabelas com pdfplumber; se não houver cabeçalho reconhecido, faz fallback por linhas de texto.
Os dicionários retornados usam as mesmas chaves do CSV INFINTY já tratado em views.py.

Bandeira como imagem (logo): localiza imagens na coluna «Bandeira», aplica reconhecimento visual
(Mastercard: círculos vermelho/laranja) e, se existir Tesseract, complementa com OCR no recorte.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
import pdfplumber

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[misc, assignment]

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore[misc, assignment]

if pytesseract is not None:
    _tcmd = os.environ.get('TESSERACT_CMD', '').strip()
    if _tcmd:
        pytesseract.pytesseract.tesseract_cmd = _tcmd

def _norm(s: str) -> str:
    if not s:
        return ''
    return ' '.join(s.replace('\n', ' ').split()).strip().lower()


def _fold_ascii(s: str) -> str:
    """Remove acentos para comparar crédito/credito etc."""
    if not s:
        return ''
    d = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in d if unicodedata.category(c) != 'Mn').lower()


def _pad_cells_to_ncols(cells: list[str | None], ncols: int) -> list[str]:
    """Garante índices alinhados ao cabeçalho (pdfplumber muitas vezes omite células vazias no fim)."""
    out = [str(c or '').strip() for c in cells]
    while len(out) < ncols:
        out.append('')
    return out


def _extract_tipo_from_row_joined(cells: list[str | None]) -> str:
    """
    Procura Crédito/Débito/Pix no texto completo da linha (palavra partida entre células).
    """
    blob = ' '.join(str(c or '').strip() for c in cells if c is not None and str(c).strip())
    if not blob:
        return ''
    if re.search(r'cr[eéèê]dito|credito', blob, re.I):
        return 'Crédito'
    if re.search(r'd[eéèê]bito|debito', blob, re.I):
        return 'Débito'
    if re.search(r'\bpix\b', blob, re.I):
        return 'Pix'
    if re.search(r'parcelado|à\s*vista|a\s*vista', blob, re.I):
        m = re.search(r'(parcelado|à\s*vista|a\s*vista)', blob, re.I)
        return m.group(0).strip() if m else ''
    return ''


def _scan_tipo_value_from_row(cells: list[str | None]) -> str:
    """
    Localiza na linha o texto da coluna «Tipo» (Crédito, Débito, etc.) quando o índice da coluna falhou.
    Ignora datas, valores monetários e nomes típicos de bandeira.
    """
    _band_kw = (
        'visa', 'master', 'mastercard', 'elo', 'amex', 'american', 'hiper', 'diners',
        'discover', 'jcb', 'cabal', 'alelo',
    )
    for c in cells:
        if c is None:
            continue
        s = str(c).replace('\ufeff', '').strip()
        if not s or len(s) > 48:
            continue
        if re.search(r'^\s*R\$\s*', s, re.I):
            continue
        if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', s):
            continue
        if re.fullmatch(r'[\d.\s,]+', s):
            continue
        fn = _fold_ascii(s)
        if any(b in fn for b in _band_kw):
            continue
        if re.search(r'credito', fn):
            return s
        if re.search(r'debito', fn):
            return s
        if re.fullmatch(r'pix', fn):
            return s
        if 'parcelado' in fn or 'vista' in fn:
            return s
    return ''


def _normalize_parcela_display(s: str) -> str:
    """Formato como no PDF: «1 / 2» com espaços em volta da barra."""
    m = re.search(r'(\d+)\s*/\s*(\d+)', str(s or ''))
    if m:
        return f'{m.group(1)} / {m.group(2)}'
    return str(s or '').strip()


def _split_parcela_combo(s: str) -> tuple[str, str]:
    m = re.search(r'(\d+)\s*/\s*(\d+)', str(s or ''))
    if m:
        return m.group(1), m.group(2)
    return '', ''


def _parse_money_cell(s: str) -> str:
    if not s:
        return ''
    t = str(s).strip()
    # remove símbolo R$ e espaços
    t = re.sub(r'R\$\s*', '', t, flags=re.I)
    t = t.replace(' ', '')
    return t


def _row_to_infinity_dict(
    cells: list[str | None],
    col_map: dict[str, int | None],
    header_ncols: int | None = None,
) -> dict[str, str] | None:
    if header_ncols is not None and header_ncols > 0:
        cells = _pad_cells_to_ncols(cells, header_ncols)

    def g(key: str) -> str:
        idx = col_map.get(key)
        if idx is None or idx >= len(cells):
            return ''
        v = cells[idx]
        return '' if v is None else str(v).strip()

    data_pag = g('data_pagamento') or g('data_pagamento_alt')
    if not data_pag:
        return None
    if not re.search(r'\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}', data_pag):
        return None

    # Tipo (Crédito/Débito) tem prioridade sobre «Forma pagamento» = Cartão
    tipo_v = g('tipo') or _extract_tipo_from_row_joined(cells) or _scan_tipo_value_from_row(cells)
    forma_v = (g('forma') or '').strip()
    if tipo_v:
        fp = tipo_v
    elif forma_v and _fold_ascii(forma_v) not in ('cartao', 'cartão', 'card'):
        fp = forma_v
    else:
        fp = forma_v or 'Cartão'

    combo = g('parcela_combo')
    if combo:
        p1, p2 = _split_parcela_combo(combo)
        parcelas_v = p1 or '1'
        total_v = p2 or '1'
        parcela_txt = _normalize_parcela_display(combo)
    else:
        parcelas_v = g('parcelas') or '1'
        total_v = g('total_parcelas') or g('parcelas') or '1'
        parcela_txt = ''

    out = {
        'Data Pagamento': data_pag,
        'Forma Pagamento': fp,
        'Bandeira': g('bandeira'),
        'Valor Bruto': _parse_money_cell(g('valor_bruto')),
        'Valor Taxa': _parse_money_cell(g('taxa')),
        'Valor Líquido': _parse_money_cell(g('liquido')),
        'Autorização': g('autorizacao') or g('nsu'),
        'Data Venda': g('data_venda') or data_pag,
        'Parcela': parcela_txt,
        'Parcelas': parcelas_v,
        'Total de Parcelas': total_v,
    }
    return out


def _build_col_map(header_row: list[str | None]) -> dict[str, int | None]:
    hdr = [str(x or '') for x in header_row]
    m: dict[str, int | None] = {
        'data_pagamento': None,
        'data_pagamento_alt': None,
        'data_venda': None,
        'tipo': None,
        'forma': None,
        'bandeira': None,
        'valor_bruto': None,
        'taxa': None,
        'liquido': None,
        'autorizacao': None,
        'nsu': None,
        'parcela_combo': None,
        'parcelas': None,
        'total_parcelas': None,
    }
    for i, cell in enumerate(hdr):
        n = _norm(cell)
        if not n:
            continue
        if 'recebimento' in n and 'data' in n:
            if m['data_pagamento'] is None:
                m['data_pagamento'] = i
            elif m['data_pagamento_alt'] is None:
                m['data_pagamento_alt'] = i
        elif 'pagamento' in n and 'data' in n:
            if m['data_pagamento'] is None:
                m['data_pagamento'] = i
            elif m['data_pagamento_alt'] is None:
                m['data_pagamento_alt'] = i
        elif 'venda' in n and 'data' in n:
            m['data_venda'] = i
        elif m['tipo'] is None and (
            n == 'tipo'
            or (
                n.startswith('tipo ')
                and len(n) < 40
                and 'document' not in n
                and 'arquivo' not in n
            )
        ):
            # Conta Web Infinite Pay: coluna «Tipo» → forma de pagamento (ex.: crédito/débito)
            m['tipo'] = i
        elif 'bandeira' in n or ('band' in n and 'eira' in n):
            m['bandeira'] = i
        elif 'forma' in n and 'pagamento' in n:
            m['forma'] = i
        elif 'bruto' in n or ('valor' in n and 'líquido' not in n and 'liquido' not in n and 'taxa' not in n):
            if m['valor_bruto'] is None and 'taxa' not in n:
                m['valor_bruto'] = i
        elif 'taxa' in n or 'tarifa' in n or 'desconto' in n:
            m['taxa'] = i
        elif 'líquido' in n or 'liquido' in n:
            m['liquido'] = i
        elif 'autoriz' in n or n == 'nsu' or 'código' in n and 'aut' in n:
            m['autorizacao'] = i
        elif 'nsu' in n or 'doc' in n:
            m['nsu'] = i
        elif n == 'parcela':
            # Infinite Pay: coluna única «Parcela» com valores «1 / 2»
            m['parcela_combo'] = i
        elif 'parcela' in n and 'total' not in n:
            if m['parcelas'] is None:
                m['parcelas'] = i
        elif 'total' in n and 'parcela' in n:
            m['total_parcelas'] = i

    # Fallbacks por ordem comum: data | data | bandeira | bruto | taxa | líquido | auth
    if m['data_pagamento'] is None and m['data_pagamento_alt'] is None:
        for i, cell in enumerate(hdr):
            if re.search(r'data', _norm(cell)) and re.search(r'pag|receb', _norm(cell)):
                m['data_pagamento'] = i
                break

    # «Tipo» às vezes não entra no cabeçalho extraído (PDF com célula gráfica); tenta de novo com texto bruto
    if m['tipo'] is None:
        for i, cell in enumerate(hdr):
            raw = str(cell or '').replace('\ufeff', '').strip()
            if _norm(raw) == 'tipo' or raw.casefold() == 'tipo':
                m['tipo'] = i
                break

    if m['bandeira'] is None:
        for i, cell in enumerate(hdr):
            raw = _norm(str(cell or ''))
            if 'band' in raw and 'eira' in raw:
                m['bandeira'] = i
                break
    return m


_TIPO_VALOR_RE = re.compile(
    r'^\s*(cr[eé]dito|credito|d[eé]bito|debito|pix|parcelado|à?\s*vista|a\s*vista)\s*$',
    re.IGNORECASE,
)


def _infer_tipo_column_from_body(
    table: list[list | None],
    start_row: int,
    ncols: int,
    min_hits: int = 2,
) -> int | None:
    """
    Descobre o índice da coluna «Tipo» (Crédito/Débito) quando o cabeçalho não veio como texto.
    """
    if ncols < 1 or start_row >= len(table):
        return None
    hits = [0] * ncols
    scanned = 0
    for r in range(start_row, len(table)):
        row = table[r]
        if not row:
            continue
        cells = [str(c or '').strip() for c in row]
        while len(cells) < ncols:
            cells.append('')
        scanned += 1
        for j in range(ncols):
            cj = cells[j]
            if (
                _TIPO_VALOR_RE.match(cj)
                or (len(cj) < 48 and re.search(r'cr[eé]dito|d[eé]bito|credito|debito', cj, re.I))
                or (_scan_tipo_value_from_row([cj]) and len(cj) < 40)
            ):
                hits[j] += 1
        if scanned >= 40:
            break
    if scanned < 1:
        return None
    best_i, best_h = max(enumerate(hits), key=lambda x: x[1])
    if best_h >= max(1, min_hits - 1) and best_h >= max(1, scanned * 0.10):
        return best_i
    return None


def _cell_is_parcela_combo_val(s: str) -> bool:
    """«1 / 2» na coluna Parcela — evita confundir com datas «01/02/2026»."""
    t = str(s or '').strip()
    if not t:
        return False
    if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', t):
        return False
    return bool(re.match(r'^\s*\d{1,3}\s*/\s*\d{1,3}\s*$', t))


def _infer_parcela_combo_column(
    table: list[list | None],
    start_row: int,
    ncols: int,
) -> int | None:
    """Coluna «Parcela» com «1 / 2» quando o cabeçalho não veio como texto."""
    if ncols < 1 or start_row >= len(table):
        return None
    hits = [0] * ncols
    scanned = 0
    for r in range(start_row, len(table)):
        row = table[r]
        if not row:
            continue
        cells = [str(c or '').strip() for c in row]
        while len(cells) < ncols:
            cells.append('')
        scanned += 1
        for j in range(ncols):
            if _cell_is_parcela_combo_val(cells[j]):
                hits[j] += 1
        if scanned >= 40:
            break
    if scanned < 1:
        return None
    best_i, best_h = max(enumerate(hits), key=lambda x: x[1])
    if best_h >= max(1, scanned * 0.15):
        return best_i
    return None


_BRAND_NAME_IN_CELL = re.compile(
    r'visa|master(?:card)?|\belo\b|amex|american|hiper|diners|discover|jcb|cabal',
    re.IGNORECASE,
)


def _infer_bandeira_column_from_body(
    table: list[list | None],
    start_row: int,
    ncols: int,
) -> int | None:
    """Quando o cabeçalho «Bandeira» não veio como texto, mas as células trazem o nome."""
    if ncols < 1 or start_row >= len(table):
        return None
    hits = [0] * ncols
    scanned = 0
    for r in range(start_row, len(table)):
        row = table[r]
        if not row:
            continue
        cells = [str(c or '').strip() for c in row]
        while len(cells) < ncols:
            cells.append('')
        scanned += 1
        for j in range(ncols):
            cj = cells[j]
            if len(cj) < 2 or len(cj) > 36:
                continue
            if _BRAND_NAME_IN_CELL.search(cj):
                hits[j] += 1
        if scanned >= 35:
            break
    if scanned < 1:
        return None
    best_i, best_h = max(enumerate(hits), key=lambda x: x[1])
    if best_h >= max(2, scanned * 0.12):
        return best_i
    return None


def _bandeira_fallback_raster_column(
    page,
    table_bbox: tuple[float, float, float, float],
    bandeira_col_idx: int,
    header_ncols: int,
    n_data_rows: int,
) -> list[str]:
    """
    Recorta a coluna Bandeira linha a linha na página renderizada (logos vetoriais nem sempre
    aparecem em page.images).
    """
    if n_data_rows < 1 or header_ncols < 1:
        return [''] * n_data_rows
    x0, top, x1, bottom = (
        float(table_bbox[0]),
        float(table_bbox[1]),
        float(table_bbox[2]),
        float(table_bbox[3]),
    )
    tw = x1 - x0
    if tw <= 0:
        return [''] * n_data_rows
    col_w = tw / float(header_ncols)
    bx0 = x0 + bandeira_col_idx * col_w
    bx1 = bx0 + col_w
    header_h = max(8.0, (bottom - top) * 0.11)
    body_top = top + header_h
    body_h = max(1.0, bottom - body_top)
    row_h = body_h / float(max(n_data_rows, 1))

    labels: list[str] = []
    try:
        page_im = page.to_image(resolution=200)
    except Exception:
        return [''] * n_data_rows

    for i in range(n_data_rows):
        y0 = body_top + i * row_h
        y1 = body_top + (i + 1) * row_h
        band = ''
        try:
            sub = page_im.crop((bx0, y0, bx1, y1))
            pil = getattr(sub, 'original', None)
            if pil is not None:
                band = _pil_logo_to_bandeira(pil)
        except Exception:
            band = ''
        labels.append(band)
    return labels[:n_data_rows]


def _normalize_bandeira_from_ocr(text: str) -> str:
    """Converte texto lido no logo (OCR) para o nome da bandeira usado no sistema."""
    if not text:
        return ''
    t = text.upper()
    t = re.sub(r'[^A-Z0-9\s]', ' ', t)
    t = ' '.join(t.split())
    if 'AMERICAN' in t or ' AMEX' in t or t == 'AX':
        return 'Amex'
    if 'MASTERCARD' in t or 'MASTER' in t or 'MASTER CARD' in t:
        return 'Mastercard'
    if 'VISA' in t or 'V1SA' in t:
        return 'Visa'
    if 'ELO' in t:
        return 'Elo'
    if 'HIPER' in t:
        return 'Hipercard'
    if 'DINERS' in t:
        return 'Diners'
    if 'DISCOVER' in t:
        return 'Discover'
    if 'JCB' in t:
        return 'JCB'
    if 'PIX' in t:
        return 'Pix'
    return ''


def _classify_bandeira_visual(pil_image) -> str:
    """
    Identifica bandeira pelo desenho do logo (sem depender só de OCR):
    - Mastercard: círculos vermelho + laranja sobrepostos
    - Elo: ícone tricolor (azul, amarelo, vermelho) + texto «elo» escuro
    - Visa: palavra em azul escuro + traço amarelo/dourado típico no «V»
    """
    if pil_image is None or np is None:
        return ''
    try:
        im = pil_image
        if hasattr(im, 'convert'):
            im = im.convert('RGB')
        arr = np.asarray(im)
        if arr.ndim != 3 or arr.shape[2] < 3:
            return ''
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h < 4 or w < 8:
            return ''

        r = arr[..., 0].astype(np.float32)
        g = arr[..., 1].astype(np.float32)
        b = arr[..., 2].astype(np.float32)

        not_white = (r + g + b) < 730

        red_all = not_white & (r > 90) & (r > g + 15) & (r > b + 12)
        orange_all = not_white & (r > 100) & (g > 65) & (b < r - 8) & (b < g)

        fr = float(np.mean(red_all))
        fo = float(np.mean(orange_all))

        mid = max(1, w // 2)
        left = arr[:, :mid]
        right = arr[:, mid:]
        rl = left[..., 0].astype(np.float32)
        gl = left[..., 1].astype(np.float32)
        bl = left[..., 2].astype(np.float32)
        rr = right[..., 0].astype(np.float32)
        gr = right[..., 1].astype(np.float32)
        br = right[..., 2].astype(np.float32)

        nwl = (rl + gl + bl) < 730
        nwr = (rr + gr + br) < 730
        red_left = float(np.mean(nwl & (rl > 88) & (rl > gl + 12) & (rl > bl + 10)))
        org_right = float(np.mean(nwr & (rr > 100) & (gr > 62) & (br < rr) & (br < gr)))

        # Marca Mastercard (símbolo só com círculos, sem palavra)
        if (fr > 0.028 and fo > 0.028 and (fr + fo) > 0.075) or (
            red_left > 0.04 and org_right > 0.04
        ):
            return 'Mastercard'

        # Elo: três segmentos no círculo (azul, amarelo, vermelho) — antes da Visa para não confundir
        elo_blue = not_white & (b > 55) & (b >= r - 8) & (b > g - 30) & (r < 170) & (g < 205)
        elo_yellow = not_white & (r > 125) & (g > 110) & (b < 140) & (r + g > 265)
        elo_red = not_white & (r > 82) & (r > g + 8) & (r > b + 6) & (g < 190) & (b < 165)
        feb = float(np.mean(elo_blue))
        fey = float(np.mean(elo_yellow))
        fer = float(np.mean(elo_red))
        if feb > 0.012 and fey > 0.01 and fer > 0.01 and (feb + fey + fer) > 0.045:
            return 'Elo'

        # Visa: azul institucional (B dominante, R/G contidos) e/ou pincelada amarela no V
        visa_navy = not_white & (b > 60) & (b >= r + 14) & (b >= g + 6) & (r < 135) & (g < 145)
        visa_gold = (
            not_white
            & (r > 165)
            & (g > 125)
            & (b < 165)
            & ((r - b) > 35)
            & ((g - b) > 15)
        )
        fn = float(np.mean(visa_navy))
        fg = float(np.mean(visa_gold))
        if (fn > 0.06 and fg > 0.002) or (fn > 0.095):
            return 'Visa'
    except Exception:
        return ''
    return ''


def _pil_logo_to_bandeira(pil_image) -> str:
    if pil_image is None:
        return ''
    try:
        im = pil_image
        if hasattr(im, 'convert'):
            im = im.convert('RGB')
        if pytesseract is not None:
            txt = pytesseract.image_to_string(im, lang='por+eng', config='--psm 6')
            out = _normalize_bandeira_from_ocr(txt)
            if out:
                return out
            txt2 = pytesseract.image_to_string(im, lang='eng', config='--psm 7')
            out2 = _normalize_bandeira_from_ocr(txt2)
            if out2:
                return out2
    except Exception:
        pass
    return _classify_bandeira_visual(pil_image)


def _bandeira_labels_from_logos(
    page,
    header_ncols: int,
    bandeira_col_idx: int,
    table_bbox: tuple[float, float, float, float],
    n_data_rows: int,
) -> list[str]:
    """
    Localiza imagens embutidas na coluna da bandeira (por posição); OCR (se houver) + reconhecimento visual.
    Pressupõe larguras de coluna uniformes dentro do retângulo da tabela.
    """
    if n_data_rows < 1 or header_ncols < 1:
        return [''] * n_data_rows

    x0, top, x1, bottom = (float(table_bbox[0]), float(table_bbox[1]), float(table_bbox[2]), float(table_bbox[3]))
    table_w = x1 - x0
    if table_w <= 0:
        return [''] * n_data_rows

    col_w = table_w / float(header_ncols)
    bx0 = x0 + bandeira_col_idx * col_w
    bx1 = bx0 + col_w

    inside: list[dict] = []
    for im in page.images or []:
        try:
            w = float(im['x1']) - float(im['x0'])
            h = float(im['bottom']) - float(im['top'])
        except (KeyError, TypeError, ValueError):
            continue
        if w < 2 or h < 2:
            continue
        # Logos podem ser um pouco mais largos que a coluna estimada (layout desigual)
        max_logo_w = max(col_w * 1.35, min(95.0, table_w * 0.42))
        if w > max_logo_w or w > table_w * 0.48:
            continue
        cx = (float(im['x0']) + float(im['x1'])) / 2.0
        cy = (float(im['top']) + float(im['bottom'])) / 2.0
        if cx < bx0 or cx > bx1:
            continue
        if cy < top - 3 or cy > bottom + 3:
            continue
        inside.append(im)

    inside.sort(key=lambda z: float(z['top']))

    if len(inside) > n_data_rows:
        if len(inside) == n_data_rows + 1:
            body_top = top + (bottom - top) * 0.1
            if float(inside[0]['bottom']) <= body_top:
                inside = inside[1:]
        inside = inside[:n_data_rows]
    elif len(inside) < n_data_rows:
        pass

    labels: list[str] = []
    try:
        page_im = page.to_image(resolution=220)
    except Exception:
        return [''] * n_data_rows

    for im in inside[:n_data_rows]:
        band = ''
        try:
            bbox = (float(im['x0']), float(im['top']), float(im['x1']), float(im['bottom']))
            sub = page_im.crop(bbox)
            pil = getattr(sub, 'original', None)
            if pil is not None:
                band = _pil_logo_to_bandeira(pil)
        except Exception:
            band = ''
        labels.append(band)

    while len(labels) < n_data_rows:
        labels.append('')
    return labels[:n_data_rows]


def _parse_tables_pdf(pdf_bytes: bytes) -> tuple[list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    out: list[dict[str, str]] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pi, page in enumerate(pdf.pages):
            tables = page.extract_tables() or []
            found_tables = page.find_tables() or []
            for ti, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue
                header = table[0]
                col_map = _build_col_map(header)
                if col_map.get('data_pagamento') is None and col_map.get('data_pagamento_alt') is None:
                    if len(table) > 2:
                        col_map = _build_col_map(table[1])
                if col_map.get('data_pagamento') is None and col_map.get('data_pagamento_alt') is None:
                    continue
                start = 1
                if not _row_to_infinity_dict([str(c or '') for c in table[1]], col_map, len(header)):
                    start = 2

                if col_map.get('tipo') is None:
                    inf_tipo = _infer_tipo_column_from_body(table, start, len(header))
                    if inf_tipo is not None:
                        col_map['tipo'] = inf_tipo

                if col_map.get('parcela_combo') is None:
                    inf_parc = _infer_parcela_combo_column(table, start, len(header))
                    if inf_parc is not None:
                        col_map['parcela_combo'] = inf_parc

                if col_map.get('bandeira') is None:
                    ib = _infer_bandeira_column_from_body(table, start, len(header))
                    if ib is not None:
                        col_map['bandeira'] = ib

                batch: list[dict[str, str]] = []
                for row in table[start:]:
                    cells = [str(c or '') for c in row]
                    if not any(cells):
                        continue
                    d = _row_to_infinity_dict(cells, col_map, len(header))
                    if d:
                        batch.append(d)

                bi = col_map.get('bandeira')
                tbox = None
                if found_tables:
                    tbox = found_tables[ti].bbox if ti < len(found_tables) else found_tables[0].bbox

                if (
                    tbox is not None
                    and bi is not None
                    and batch
                    and any(not (x.get('Bandeira') or '').strip() for x in batch)
                ):
                    labels = _bandeira_labels_from_logos(
                        page,
                        len(header),
                        bi,
                        tbox,
                        len(batch),
                    )
                    for i, d in enumerate(batch):
                        if i < len(labels) and labels[i] and not (d.get('Bandeira') or '').strip():
                            d['Bandeira'] = labels[i]
                    if any(not (x.get('Bandeira') or '').strip() for x in batch):
                        rast = _bandeira_fallback_raster_column(
                            page, tbox, bi, len(header), len(batch)
                        )
                        for i, d in enumerate(batch):
                            if i < len(rast) and rast[i] and not (d.get('Bandeira') or '').strip():
                                d['Bandeira'] = rast[i]

                if batch:
                    out.extend(batch)
                    warnings.append(f'Tabela extraída na página {pi + 1} (bloco {ti + 1}).')

    return out, warnings


DATE_RE = re.compile(
    r'\b(\d{2}/\d{2}/\d{4})\b|\b(\d{4}-\d{2}-\d{2})\b'
)
MONEY_RE = re.compile(
    r'R\$\s*([\d]{1,3}(?:\.[\d]{3})*,\d{2})|([\d]{1,3}(?:\.[\d]{3})*,\d{2})|(\d+,\d{2})'
)


def _parse_text_fallback(pdf_bytes: bytes) -> tuple[list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    out: list[dict[str, str]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full = []
        for page in pdf.pages:
            t = page.extract_text() or ''
            full.append(t)
    text = '\n'.join(full)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        dates = DATE_RE.findall(ln)
        flat_dates = []
        for a in dates:
            flat_dates.extend([x for x in a if x])
        moneys = MONEY_RE.findall(ln)
        valores: list[str] = []
        for m in moneys:
            valores.extend([x for x in m if x])
        if len(flat_dates) < 1 or len(valores) < 2:
            continue
        data_pag = flat_dates[0]
        data_venda = flat_dates[1] if len(flat_dates) > 1 else data_pag
        bruto = valores[0].replace('.', '').replace(',', '.') if valores else ''
        liquido = valores[-1].replace('.', '').replace(',', '.') if valores else ''
        taxa = ''
        if len(valores) >= 3:
            try:
                b = float(valores[0].replace('.', '').replace(',', '.'))
                l_ = float(valores[-1].replace('.', '').replace(',', '.'))
                taxa = f'{abs(b - l_):.2f}'.replace('.', ',')
            except ValueError:
                taxa = valores[1] if len(valores) > 1 else ''

        auth = ''
        am = re.search(r'\b(\d{6,20})\b', ln)
        if am:
            auth = am.group(1)

        out.append(
            {
                'Data Pagamento': data_pag,
                'Forma Pagamento': 'Cartão',
                'Bandeira': '',
                'Valor Bruto': valores[0] if valores else '',
                'Valor Taxa': taxa,
                'Valor Líquido': valores[-1] if valores else '',
                'Autorização': auth,
                'Data Venda': data_venda,
                'Parcelas': '1',
                'Total de Parcelas': '1',
            }
        )
    if out:
        warnings.append('Linhas obtidas por análise de texto (fallback); confira os valores na prévia.')
    return out, warnings


def parse_infinitepay_pdf_bytes(pdf_bytes: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """
    Retorna lista de dicts com chaves compatíveis com o fluxo INFINTY do CSV e avisos.
    """
    rows, w1 = _parse_tables_pdf(pdf_bytes)
    if rows:
        return rows, w1
    rows2, w2 = _parse_text_fallback(pdf_bytes)
    return rows2, w1 + w2
