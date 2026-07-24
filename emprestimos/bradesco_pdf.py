"""
Parser do Documento Descritivo de Crédito / Evolução de Dívida (Bradesco).

Preferência: texto embutido (pdfplumber).
Fallback: OCR (Tesseract) quando o PDF for só imagem.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pdfplumber

_TESSDATA_LOCAL = Path(__file__).resolve().parent.parent / 'tessdata'


def _dec(texto: str | None) -> Decimal:
    if not texto:
        return Decimal('0')
    t = str(texto).strip()
    t = re.sub(r'^(?:R\$|RS)\s*', '', t, flags=re.I).strip()
    t = t.replace(' ', '')
    # OCR: 8.07664 (perdeu a vírgula) → 8.076,64
    if re.fullmatch(r'\d{1,3}\.\d{5}', t):
        t = t[:-2] + ',' + t[-2:]
    # OCR: 50,000,00
    if re.fullmatch(r'\d{1,3}(,\d{3})+,\d{2}', t):
        t = t[:-3].replace(',', '') + '.' + t[-2:]
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+,\d{2}', t):
        t = t.replace('.', '').replace(',', '.')
    elif ',' in t and '.' in t:
        if t.rfind(',') > t.rfind('.'):
            t = t.replace('.', '').replace(',', '.')
        else:
            t = t.replace(',', '')
    elif ',' in t:
        partes = t.split(',')
        if len(partes) == 2 and len(partes[1]) <= 2:
            t = partes[0].replace('.', '') + '.' + partes[1]
        else:
            t = t.replace(',', '')
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _dec_pct(texto: str | None) -> Decimal:
    if not texto:
        return Decimal('0')
    t = str(texto).replace('%', '').strip()
    t = re.sub(r'^(?:R\$|RS)\s*', '', t, flags=re.I).strip()
    # Percentual BR: 60,844 ou 4,04 (vírgula = decimal)
    if re.fullmatch(r'\d+,\d{1,4}', t):
        t = t.replace(',', '.')
    elif re.fullmatch(r'\d+\.\d{1,4}', t):
        pass
    else:
        return _dec(t)
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _parse_data(texto: str | None) -> date | None:
    if not texto:
        return None
    t = texto.strip()
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _campo(texto: str, padrao: str) -> str | None:
    m = re.search(padrao, texto, flags=re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


def _configurar_tesseract() -> None:
    import pytesseract

    for cmd in (
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ):
        if os.path.isfile(cmd):
            pytesseract.pytesseract.tesseract_cmd = cmd
            break
    if _TESSDATA_LOCAL.is_dir() and any(_TESSDATA_LOCAL.glob('*.traineddata')):
        os.environ['TESSDATA_PREFIX'] = str(_TESSDATA_LOCAL)


def _ocr_score_texto(txt: str) -> int:
    """Quantas linhas parecem parcela (data + ≥3 valores monetários)."""
    n = 0
    for ln in (txt or '').splitlines():
        if re.search(r'\d{2}/\d{2}/\d{4}', ln) and len(
            re.findall(r'(?:R\$|RS)\s*[\d.,]+', ln, flags=re.I)
        ) >= 3:
            n += 1
    return n


def _ocr_uma_imagem(pil) -> str:
    import pytesseract

    try:
        return pytesseract.image_to_string(pil, lang='por+eng', config='--psm 6') or ''
    except Exception:
        try:
            return pytesseract.image_to_string(pil, lang='por', config='--psm 6') or ''
        except Exception:
            return pytesseract.image_to_string(pil, lang='eng', config='--psm 6') or ''


def _ocr_mesclar_textos(textos: list[str]) -> str:
    """
    Une várias leituras OCR: para cada data de vencimento mantém a linha
    com mais valores R$/RS (tabela Bradesco).
    """
    por_data: dict[str, tuple[int, str]] = {}
    cabecalhos: list[str] = []
    for txt in textos:
        for ln in (txt or '').replace('\r', '\n').splitlines():
            s = ln.strip()
            if not s:
                continue
            m = re.search(r'(\d{2}/\d{2}/\d{4})', s)
            if not m:
                if not cabecalhos or s not in cabecalhos:
                    # guarda cabeçalho só do melhor texto (depois)
                    cabecalhos.append(s)
                continue
            data = m.group(1)
            score = len(re.findall(r'(?:R\$|RS)\s*[\d.,]+', s, flags=re.I))
            if 'PARCELA' in s.upper():
                score += 2
            ant = por_data.get(data)
            if ant is None or score > ant[0]:
                por_data[data] = (score, s)

    # Cabeçalho: texto com mais linhas boas
    melhor_cab = max(textos, key=_ocr_score_texto) if textos else ''
    cab_linhas = []
    for ln in melhor_cab.replace('\r', '\n').splitlines():
        if re.search(r'\d{2}/\d{2}/\d{4}', ln) and re.search(r'(?:R\$|RS)\s*[\d.,]+', ln, re.I):
            break
        cab_linhas.append(ln)

    datas_ord = sorted(
        por_data.keys(),
        key=lambda d: _parse_data(d) or date.min,
    )
    corpo = [por_data[d][1] for d in datas_ord]
    return '\n'.join(cab_linhas + corpo)


def _ocr_pdf(file_obj) -> str:
    import pytesseract
    from PIL import ImageEnhance, ImageOps

    _configurar_tesseract()
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    partes: list[str] = []
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            # 350dpi + contraste: tabelas densas (ex.: 16939567) falhavam em 300dpi
            im = page.to_image(resolution=350)
            pil = im.original.convert('RGB')
            g = ImageOps.grayscale(pil)
            variantes = [
                ImageEnhance.Contrast(g).enhance(1.6),
                ImageEnhance.Sharpness(ImageEnhance.Contrast(g).enhance(2.0)).enhance(1.8),
                g.point(lambda x: 0 if x < 160 else 255),
            ]
            textos = [_ocr_uma_imagem(v) for v in variantes]
            # também tenta a página colorida original
            textos.append(_ocr_uma_imagem(pil))
            partes.append(_ocr_mesclar_textos(textos))
    return '\n'.join(partes)


def extrair_texto_bradesco(file_obj) -> str:
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    with pdfplumber.open(file_obj) as pdf:
        texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    if texto.strip():
        return texto
    return _ocr_pdf(file_obj)


def _parece_bradesco(texto: str) -> bool:
    u = texto.upper()
    return (
        'BRADESCO' in u
        or 'DOCUMENTO DESCRITIVO DE CR' in u
        or 'DOCUMENTO DE EVOLU' in u
        or 'PARCELA A VENCER' in u
        or ('PARCELA PAGA' in u and 'SHOPCREDIT' in u)
    )


def _normalizar_texto(texto: str) -> str:
    t = texto.replace('\r', '\n')
    t = t.replace('RS ', 'R$ ').replace('R$ ', 'R$ ')
    t = re.sub(r'[ \t]+', ' ', t)
    return t


def _alinhar_amort_juros_price(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Na Tabela Price a amortização sobe e os juros caem.
    Se OCR inverter amort/juros, troca quando a soma fecha a parcela.
    """
    if len(rows) < 4:
        return rows
    rows = sorted(rows, key=lambda r: r['numero'])
    # Conta quantas vezes amort sobe vs cai
    sobe = cai = 0
    for i in range(1, len(rows)):
        d = (rows[i]['amortizacao'] or 0) - (rows[i - 1]['amortizacao'] or 0)
        if d > 1:
            sobe += 1
        elif d < -1:
            cai += 1
    if sobe >= cai:
        return rows
    # Curva invertida: troca amort↔juros quando parcela ≈ soma
    for r in rows:
        a = r.get('amortizacao') or Decimal('0')
        j = r.get('juros') or Decimal('0')
        p = r.get('valor_parcela') or Decimal('0')
        if p > 0 and abs((a + j) - p) <= Decimal('0.05'):
            r['amortizacao'], r['juros'] = j, a
    return rows


def _corrigir_valores_ocr(brutos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    OCR às vezes omite a coluna da parcela ou a amortização.
    Usa a moda do valor da parcela (PMT Price) para remontar.
    """
    from collections import Counter

    if len(brutos) < 3:
        return brutos
    vals = [
        (r['valor_parcela'] or Decimal('0')).quantize(Decimal('0.01'))
        for r in brutos
        if (r.get('valor_parcela') or 0) > 100
    ]
    if not vals:
        return brutos
    pmt, freq = Counter(vals).most_common(1)[0]
    if freq < max(3, len(brutos) // 4):
        return brutos

    for r in brutos:
        vp = r.get('valor_parcela') or Decimal('0')
        amort = r.get('amortizacao') or Decimal('0')
        juros = r.get('juros') or Decimal('0')
        # Caso: leu amort+juros+saldo sem a parcela (ex.: 1000,40 + 1917,32 = 2917,72)
        if vp > 0 and amort > 0 and abs((vp + amort) - pmt) <= Decimal('0.05'):
            r['valor_parcela'] = pmt
            r['juros'] = amort
            r['amortizacao'] = vp
            if r.get('status') == 'paga':
                r['valor_pago'] = pmt
            continue
        # Caso: leu parcela + juros + saldo (amort omitida)
        if abs(vp - pmt) <= Decimal('0.05') and juros == 0 and Decimal('0') < amort < vp:
            r['juros'] = amort
            r['amortizacao'] = (vp - amort).quantize(Decimal('0.01'))
            continue
        # Caso: parcela correta mas juros zerado — recalcula
        if abs(vp - pmt) <= Decimal('0.05') and juros == 0 and amort > 0 and amort < vp:
            r['juros'] = (vp - amort).quantize(Decimal('0.01'))
    return brutos


def _renumerar_por_data(
    brutos: list[dict[str, Any]],
    prazo_parcelas: int | None = None,
) -> list[dict[str, Any]]:
    """
    OCR costuma perder o nº da parcela; ordena por vencimento e renumerada.
    Se prazo=42 e há 41 linhas → começa na 2 (1ª omitida no PDF).
    """
    if not brutos:
        return []
    # Uma linha por data (mantém a mais completa)
    por_data: dict[date, dict[str, Any]] = {}
    for r in brutos:
        d = r['data_vencimento']
        ant = por_data.get(d)
        if ant is None:
            por_data[d] = r
            continue
        # Prefere linha com nº OCR e valores > 0
        score_r = (1 if r.get('_num_ocr') else 0) + (1 if r['valor_parcela'] > 0 else 0)
        score_a = (1 if ant.get('_num_ocr') else 0) + (1 if ant['valor_parcela'] > 0 else 0)
        if score_r >= score_a:
            por_data[d] = r
    rows = sorted(por_data.values(), key=lambda x: x['data_vencimento'])

    start = 1
    if prazo_parcelas and len(rows) <= prazo_parcelas:
        start = max(1, prazo_parcelas - len(rows) + 1)

    # Âncoras OCR: ajusta início se bater com a sequência
    for i, r in enumerate(rows):
        n_ocr = r.get('_num_ocr')
        if not n_ocr:
            continue
        cand = n_ocr - i
        if cand >= 1 and abs(cand - start) <= 2:
            start = cand
            break
        if cand >= 1 and not prazo_parcelas:
            start = cand
            break

    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        item = dict(r)
        item['numero'] = start + i
        item.pop('_num_ocr', None)
        out.append(item)
    return out


def _parse_parcelas_bradesco(
    texto: str,
    prazo_parcelas: int | None = None,
) -> list[dict[str, Any]]:
    """
    Linha (texto nativo):
    5 16/08/2026 R$ 1.590,70 R$ 726,10 R$ 864,60 R$ 1.543,13 PARCELA A VENCER
    → nº | venc | parcela | principal(amort) | juros | saldo | status

    OCR: nº pode faltar; status pode faltar — usa data + valores.
    """
    linha_re = re.compile(
        r'(?m)^(?P<num>\d{1,3})\s+'
        r'(?P<venc>\d{2}/\d{2}/\d{4})\s+'
        r'R\$\s*(?P<parc>[\d.,]+)\s+'
        r'R\$\s*(?P<amort>[\d.,]+)\s+'
        r'R\$\s*(?P<juros>[\d.,]+)\s+'
        r'R\$\s*(?P<saldo>[\d.,]+)\s+'
        r'(?P<status>PARCELA\s+(?:PAGA|A\s+VENCER))',
        flags=re.IGNORECASE,
    )
    # OCR: lixo à esquerda (| 6 [data]); nº opcional; status opcional
    linha_ocr = re.compile(
        r'(?m)^(?P<head>.*?)'
        r'(?P<venc>\d{2}/\d{2}/\d{4})\D+'
        r'(?P<body>(?:R\$|RS)\s*[\d.,].+?)'
        r'(?:\s+(?P<status>PARCELA\s+(?:PAGA|A\s*VENCER)))?\s*$',
        flags=re.IGNORECASE,
    )
    money_re = re.compile(r'(?:R\$|RS)\s*([\d.,]+)', flags=re.IGNORECASE)
    num_head_re = re.compile(r'(?:^|[^\d])(\d{1,3})\s*$')

    brutos: list[dict[str, Any]] = []
    seen_dates: set[date] = set()

    for m in linha_re.finditer(texto):
        num = int(m.group('num'))
        venc = _parse_data(m.group('venc'))
        if not venc or num < 1:
            continue
        if venc in seen_dates:
            continue
        seen_dates.add(venc)
        paga = 'PAGA' in m.group('status').upper() and 'VENCER' not in m.group('status').upper()
        valor_parcela = _dec(m.group('parc'))
        amortizacao = _dec(m.group('amort'))
        juros = _dec(m.group('juros'))
        saldo = _dec(m.group('saldo'))
        brutos.append({
            'numero': num,
            '_num_ocr': num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': venc if paga else None,
            'historico': 'PARCELA PAGA' if paga else 'PARCELA A VENCER',
            'valor_pago': valor_parcela if paga else None,
            'mora': Decimal('0'),
            'iof': Decimal('0'),
            'correcao': Decimal('0'),
            'status': 'paga' if paga else 'aberta',
            '_saldo': saldo,
        })

    # Texto nativo bem formado e quase completo → mantém numeração
    if brutos and all(r.get('_num_ocr') for r in brutos) and len(brutos) >= 3:
        nums = sorted(r['numero'] for r in brutos)
        continuo = nums[-1] - nums[0] + 1 == len(nums)
        completo = (
            not prazo_parcelas
            or len(brutos) >= max(1, prazo_parcelas - 1)
        )
        if continuo and completo:
            for r in brutos:
                r.pop('_num_ocr', None)
                r.pop('_saldo', None)
            brutos.sort(key=lambda r: r['numero'])
            return brutos
        # Parcial: continua no OCR para complementar

    # Fallback OCR / linhas incompletas
    for m in linha_ocr.finditer(texto.replace('\r', '\n')):
        venc = _parse_data(m.group('venc'))
        if not venc or venc in seen_dates:
            continue
        moneys = money_re.findall(m.group('body') or '')
        if len(moneys) < 3:
            continue
        valor_parcela = _dec(moneys[0])
        amortizacao = _dec(moneys[1])
        juros = _dec(moneys[2])
        saldo = _dec(moneys[3]) if len(moneys) > 3 else Decimal('0')
        # OCR com 3 colunas (sem juros): juros = parcela − amort
        if len(moneys) == 3 and valor_parcela > 0 and amortizacao > 0:
            # Se a 3ª parece saldo (menor que parcela e próxima do saldo típico), recalcula juros
            if amortizacao < valor_parcela and juros > valor_parcela * Decimal('0.5'):
                # 3ª coluna provavelmente é saldo, não juros
                saldo = juros
                juros = (valor_parcela - amortizacao).quantize(Decimal('0.01'))
            elif juros == 0:
                juros = max(Decimal('0'), (valor_parcela - amortizacao).quantize(Decimal('0.01')))
        if valor_parcela <= 0 and amortizacao <= 0:
            continue

        status_raw = (m.group('status') or '').upper()
        if status_raw:
            paga = 'PAGA' in status_raw and 'VENCER' not in status_raw
        else:
            paga = saldo == 0 and valor_parcela > 0

        head = (m.group('head') or '').strip()
        num_ocr = None
        mh = num_head_re.search(head.replace('|', ' ').replace('[', ' ').replace(']', ' '))
        if mh:
            cand = int(mh.group(1))
            if 1 <= cand <= 600:
                num_ocr = cand
        # Também "25 27/01/2028" capturado no head
        mh2 = re.search(r'(\d{1,3})\s*$', head.strip())
        if mh2:
            cand = int(mh2.group(1))
            if 1 <= cand <= 600:
                num_ocr = cand

        seen_dates.add(venc)
        brutos.append({
            'numero': num_ocr or 0,
            '_num_ocr': num_ocr,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': venc if paga else None,
            'historico': 'PARCELA PAGA' if paga else 'PARCELA A VENCER',
            'valor_pago': valor_parcela if paga else None,
            'mora': Decimal('0'),
            'iof': Decimal('0'),
            'correcao': Decimal('0'),
            'status': 'paga' if paga else 'aberta',
            '_saldo': saldo,
        })

    brutos = _corrigir_valores_ocr(brutos)
    out = _renumerar_por_data(brutos, prazo_parcelas=prazo_parcelas)
    out = _alinhar_amort_juros_price(out)
    for r in out:
        r.pop('_saldo', None)
    return out


def parse_extrato_bradesco(file_obj) -> dict[str, Any]:
    texto_raw = extrair_texto_bradesco(file_obj)
    if not texto_raw.strip():
        raise ValueError(
            'Não foi possível ler o PDF Bradesco. '
            'Se for PDF em imagem, instale o Tesseract OCR (idioma português).'
        )
    if not _parece_bradesco(texto_raw):
        raise ValueError('PDF não parece ser o Documento de Evolução de Dívida Bradesco.')

    texto = _normalizar_texto(texto_raw)
    # OCR costuma ler "RS" em vez de "R$"
    texto_raw_norm = re.sub(r'\bRS\b', 'R$', texto_raw, flags=re.I)
    linhas = [ln.strip() for ln in texto_raw_norm.replace('\r', '\n').splitlines() if ln.strip()]

    # Contrato: linha "NNNNNNNN DD/MM/AAAA HH:MM:SS" após "Número do Contrato"
    numero_contrato = None
    m_ctr = re.search(
        r'N[uúú]mero\s+do\s+Contrato.*?(\d{6,12})\s+(\d{2}/\d{2}/\d{4})',
        texto_raw,
        flags=re.I | re.S,
    )
    if m_ctr:
        numero_contrato = m_ctr.group(1)
        data_contratacao = _parse_data(m_ctr.group(2))
    else:
        data_contratacao = None
        for ln in linhas:
            m = re.match(r'^(\d{6,12})\s+(\d{2}/\d{2}/\d{4})(?:\s+\d{1,2}:\d{2}:\d{2})?$', ln)
            if m:
                numero_contrato = m.group(1)
                data_contratacao = _parse_data(m.group(2))
                break
    if not numero_contrato:
        raise ValueError('Número do contrato não encontrado no PDF Bradesco.')

    cliente = ''
    for i, ln in enumerate(linhas):
        if re.search(r'Nome\s+CPF/CNPJ', ln, re.I) and i + 1 < len(linhas):
            prox = linhas[i + 1]
            m_cli = re.match(
                r'^(.+?)\s+\d{2,3}\.\d{3}\.\d{3}/',
                prox,
            )
            cliente = (m_cli.group(1) if m_cli else prox).strip()
            break

    valor_contrato = Decimal('0')
    for i, ln in enumerate(linhas):
        if re.search(r'Valor\s+da\s+Opera', ln, re.I):
            # mesma linha ou próxima
            bloco = ln
            if i + 1 < len(linhas):
                bloco += ' ' + linhas[i + 1]
            m_v = re.search(r'(?:R\$|RS)\s*([\d.,]+)', bloco, flags=re.I)
            if m_v:
                valor_contrato = _dec(m_v.group(1))
            break

    # Tributos / Seguros / Tarifas  →  "R$ 668,13 NAO SE APLICA R$ 772,06"
    valor_tributos = Decimal('0')
    valor_tarifas = Decimal('0')
    for i, ln in enumerate(linhas):
        if re.search(r'Tributos\s+Seguros\s+Tarifas', ln, re.I) and i + 1 < len(linhas):
            vals = re.findall(r'(?:R\$|RS)\s*([\d.,]+)', linhas[i + 1], flags=re.I)
            if vals:
                valor_tributos = _dec(vals[0])
            if len(vals) >= 2:
                valor_tarifas = _dec(vals[-1])
            break

    # Registros / Pagtos. Servs. Terceiros  →  "R$ 0,00 R$ 0,00"
    valor_registros = Decimal('0')
    valor_servicos_terceiros = Decimal('0')
    for i, ln in enumerate(linhas):
        if re.search(r'Registros\s+Pagtos', ln, re.I) and i + 1 < len(linhas):
            vals = re.findall(r'(?:R\$|RS)\s*([\d.,]+)', linhas[i + 1], flags=re.I)
            if vals:
                valor_registros = _dec(vals[0])
            if len(vals) >= 2:
                valor_servicos_terceiros = _dec(vals[1])
            break

    # Saldo Devedor Atualizado: "23 19 R$ 20.916,61"
    saldo_devedor_atualizado = Decimal('0')
    for i, ln in enumerate(linhas):
        if re.search(r'Saldo\s+Devedor\s+Atualizado', ln, re.I) and i + 1 < len(linhas):
            m_sd = re.search(r'(?:R\$|RS)\s*([\d.,]+)', linhas[i + 1], flags=re.I)
            if m_sd:
                saldo_devedor_atualizado = _dec(m_sd.group(1))
            break
    if not saldo_devedor_atualizado:
        m_sd2 = re.search(
            r'Prazo\s+Total.*?(\d{1,3})\s+(\d{1,3})\s+(?:R\$|RS)\s*([\d.,]+)',
            texto_raw_norm,
            flags=re.I | re.S,
        )
        if m_sd2:
            saldo_devedor_atualizado = _dec(m_sd2.group(3))

    data_operacao = data_contratacao
    m_lib = re.search(
        r'Data\s+Libera[cç][aã]o\s+do\s+Cr[eé]dito.*?(\d{2}/\d{2}/\d{4})',
        texto_raw,
        flags=re.I | re.S,
    )
    if m_lib:
        data_operacao = _parse_data(m_lib.group(1)) or data_operacao
    else:
        for ln in linhas:
            if 'DEBITO EM CONTA' in ln.upper() or 'DÉBITO EM CONTA' in ln.upper():
                m = re.search(r'(\d{2}/\d{2}/\d{4})', ln)
                if m:
                    data_operacao = _parse_data(m.group(1))
                break

    data_vencimento = None
    m_uv = re.search(
        r'Data\s+do\s+[UÚ]ltimo\s+Vencimento.*?(\d{2}/\d{2}/\d{4})',
        texto_raw,
        flags=re.I | re.S,
    )
    if m_uv:
        data_vencimento = _parse_data(m_uv.group(1))
    else:
        for i, ln in enumerate(linhas):
            if re.search(r'[UÚ]ltimo\s+Vencimento', ln, re.I) and i + 1 < len(linhas):
                data_vencimento = _parse_data(
                    _campo(linhas[i + 1], r'(\d{2}/\d{2}/\d{4})')
                )
                break

    data_extrato = _parse_data(_campo(texto, r'Emiss[aã]o\s+(\d{2}/\d{2}/\d{4})'))

    taxa_juros_am = Decimal('0')
    taxa_juros_aa = Decimal('0')
    # "4,04 % a.m. 60,844 % a.a. 4,76 % a.m. 74,64 % a.a."
    m_tax = re.search(
        r'([\d.,]+)\s*%\s*a\.m\.\s+([\d.,]+)\s*%\s*a\.a\.',
        texto,
        flags=re.I,
    )
    if m_tax:
        taxa_juros_am = _dec_pct(m_tax.group(1))
        taxa_juros_aa = _dec_pct(m_tax.group(2))

    prazo_parcelas = None
    m_pz = re.search(
        r'Prazo\s+Total\s+da\s+Opera[cç][aã]o.*?(\d{1,3})\s+(\d{1,3})\s+R\$',
        texto_raw,
        flags=re.I | re.S,
    )
    if m_pz:
        prazo_parcelas = int(m_pz.group(1))
    else:
        for i, ln in enumerate(linhas):
            if re.search(r'Prazo\s+Total', ln, re.I) and i + 1 < len(linhas):
                m = re.match(r'^(\d{1,3})\s+(\d{1,3})\s+R\$', linhas[i + 1])
                if m:
                    prazo_parcelas = int(m.group(1))
                break

    modalidade = 'DEBITO EM CONTA CORRENTE'
    for ln in linhas:
        if 'DEBITO EM CONTA' in ln.upper() or 'DÉBITO EM CONTA' in ln.upper():
            modalidade = 'DEBITO EM CONTA CORRENTE'
            break

    parcelas = _parse_parcelas_bradesco(texto_raw, prazo_parcelas=prazo_parcelas)
    if not parcelas:
        parcelas = _parse_parcelas_bradesco(texto, prazo_parcelas=prazo_parcelas)
    if not parcelas:
        raise ValueError('Nenhuma parcela encontrada no PDF Bradesco.')

    if not data_vencimento and parcelas:
        data_vencimento = max(p['data_vencimento'] for p in parcelas)
    if not data_operacao and parcelas:
        data_operacao = min(p['data_vencimento'] for p in parcelas)

    aviso = None
    if prazo_parcelas and len(parcelas) < prazo_parcelas:
        aviso = (
            f'Prazo total no PDF: {prazo_parcelas} parcelas; '
            f'lidas {len(parcelas)}.'
        )

    return {
        'banco': 'bradesco',
        'numero_contrato': str(numero_contrato).strip(),
        'cooperativa': '',
        'cliente': (cliente or '')[:250],
        'modalidade': modalidade[:200],
        'data_operacao': data_operacao,
        'data_vencimento': data_vencimento,
        'prazo_dias': None,
        'valor_contrato': valor_contrato or Decimal('0'),
        'valor_tributos': valor_tributos or Decimal('0'),
        'valor_tarifas': valor_tarifas or Decimal('0'),
        'valor_registros': valor_registros or Decimal('0'),
        'valor_servicos_terceiros': valor_servicos_terceiros or Decimal('0'),
        'saldo_devedor_atualizado': saldo_devedor_atualizado or Decimal('0'),
        'taxa_juros_am': taxa_juros_am or Decimal('0'),
        'taxa_juros_aa': taxa_juros_aa or Decimal('0'),
        'taxa_multa_am': Decimal('0'),
        'taxa_mora_am': Decimal('0'),
        'indice_correcao': '',
        'indice_correcao_atraso': '',
        'pct_correcao_am': Decimal('0'),
        'pct_correcao_atraso_am': Decimal('0'),
        'indicador_calculo': '15-Tabela Price',
        'data_extrato': data_extrato,
        'parcelas': parcelas,
        'aviso': aviso,
        'prazo_parcelas': prazo_parcelas,
    }


def _completar_campos_custos(dados: dict[str, Any]) -> dict[str, Any]:
    """Garante chaves de custos/saldo (Sicoob não traz → zero)."""
    for k in (
        'valor_tributos',
        'valor_tarifas',
        'valor_registros',
        'valor_servicos_terceiros',
        'saldo_devedor_atualizado',
    ):
        if k not in dados or dados[k] is None:
            dados[k] = Decimal('0')
    return dados


def detectar_e_parsear_pdf_emprestimo(file_obj) -> dict[str, Any]:
    """
    Detecta Sicoob ou Bradesco e devolve o dict padronizado de importação.
    """
    from .sicoob_pdf import parse_extrato_sicoob

    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    texto_amostra = ''
    try:
        with pdfplumber.open(file_obj) as pdf:
            texto_amostra = '\n'.join((p.extract_text() or '') for p in pdf.pages[:2])
    except Exception:
        texto_amostra = ''
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)

    u = texto_amostra.upper()

    # Bradesco (texto nativo ou PDF só imagem → OCR dentro do parser)
    if _parece_bradesco(texto_amostra) or not texto_amostra.strip():
        try:
            return _completar_campos_custos(parse_extrato_bradesco(file_obj))
        except Exception as exc_br:
            if not texto_amostra.strip():
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                try:
                    dados = parse_extrato_sicoob(file_obj)
                    dados.setdefault('banco', 'sicoob')
                    return _completar_campos_custos(dados)
                except Exception:
                    raise ValueError(str(exc_br)) from None
            raise

    if (
        'SICOOB' in u
        or 'SISBR' in u
        or 'EXTRATO DE OPERA' in u
        or 'NÚMERO CONTRATO' in u
        or 'NUMERO CONTRATO' in u
    ):
        dados = parse_extrato_sicoob(file_obj)
        dados.setdefault('banco', 'sicoob')
        return _completar_campos_custos(dados)

    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    try:
        dados = parse_extrato_sicoob(file_obj)
        dados.setdefault('banco', 'sicoob')
        return _completar_campos_custos(dados)
    except Exception:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        return _completar_campos_custos(parse_extrato_bradesco(file_obj))
