"""
Parser do Demonstrativo de Evolução Contratual (Caixa Econômica Federal).

Preferência: texto embutido (pdfplumber).
Fallback: OCR (Tesseract), reutilizando o pipeline do Bradesco para PDFs em imagem.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from .bradesco_pdf import extrair_texto_bradesco
from .sicoob_pdf import _dec, _dec_pct, _parse_data, normalizar_indicador_calculo


def parece_caixa(texto: str) -> bool:
    u = _texto_busca_caixa(texto)
    return (
        'CAIXA.GOV' in u
        or 'SAC CAIXA' in u
        or 'EVOLU' in u and 'CONTRATUAL' in u
        or 'DEMOSTRATIVO DE EVOL' in u
        or (('NR. CONTRATO' in u or 'NR CONTRATO' in u) and 'SISTEMA DE PAGAMENTO' in u)
        or _eh_caixa_simulacao(texto)
    )


def _texto_busca_caixa(texto: str) -> str:
    t = (texto or '').upper()
    t = re.sub(r'[^\w\s/%,.:()-]', ' ', t, flags=re.UNICODE)
    t = re.sub(r'\s+', ' ', t)
    return t


def _eh_caixa_simulacao(texto: str) -> bool:
    t = _texto_busca_caixa(texto)
    return bool(
        re.search(r'SIMUL\w*\s+DE\s+EVOLU\w*\s+TEORICA', t)
        or ('MOSTRAR EVOLUCAO DO CONTRATO' in t and 'TOTAL FINANCIADO' in t)
        or ('PRICE/TR' in t and 'TOTAL FINANCIADO' in t and 'PRAZO TOTAL' in t)
    )


def _extrair_numero_contrato_caixa(texto: str) -> str | None:
    for padrao in (
        r'Nr\.?\s*Contrato:\s*([0-9.\-/]+)',
        r'Contrato:\s*([0-9.\-/]+)',
        r'N[uú]mero\s+do\s+Contrato:\s*([0-9.\-/]+)',
    ):
        m = re.search(padrao, texto, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_parcelas_caixa_simulacao(
    texto: str,
    data_referencia: date | None = None,
) -> list[dict[str, Any]]:
    """
    Extrato / Simulação Price+TR:
      Nº Data Prestação CorreçãoTR Juros Pagamento Saldo
      1  02/04/2026 936,10 8.539,48 7.609,33 16.148,81 532.863,93

    Pagamento mensal ≈ juros + correção TR; amortização = redução do saldo devedor.
    Parcelas com vencimento anterior à data de referência → quitadas (paga).
    """
    if data_referencia is None:
        data_referencia = date.today()
    saldo_ini_re = re.compile(
        r'^0\s+(?P<venc>\d{2}/\d{2}/\d{4})\s+(?P<saldo>[\d.,]+)\s*$',
        flags=re.MULTILINE,
    )
    parcela_re = re.compile(
        r'(?P<num>\d{1,2})\s+(?P<venc>\d{2}/\d{2}/\d{4})\s+'
        r'(?:[\d.,]+\s+\*\s+)?'
        r'(?P<prestacao>[\d.,]+)\s+'
        r'(?P<correcao>[\d.,]+)\s+'
        r'(?P<juros_col>[\d.,]+)\s+'
        r'(?P<pagamento>[\d.,]+)\s+'
        r'(?P<saldo>[\d.,]+)',
        flags=re.MULTILINE,
    )

    saldo_anterior = Decimal('0')
    m0 = saldo_ini_re.search(texto)
    if m0:
        saldo_anterior = _dec(m0.group('saldo'))

    parcelas: list[dict[str, Any]] = []
    for m in parcela_re.finditer(texto):
        num = int(m.group('num'))
        if num < 1:
            continue
        venc = _parse_data(m.group('venc'))
        if not venc:
            continue

        valor_parcela = _dec(m.group('pagamento'))
        correcao = _dec(m.group('correcao'))
        juros = _dec(m.group('juros_col'))
        saldo = _dec(m.group('saldo'))
        amortizacao = max(Decimal('0'), (saldo_anterior - saldo).quantize(Decimal('0.01')))
        saldo_anterior = saldo

        paga = bool(venc < data_referencia)

        parcelas.append({
            'numero': num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': venc if paga else None,
            'historico': 'Simulação Caixa Price/TR',
            'valor_pago': valor_parcela if paga else Decimal('0'),
            'mora': Decimal('0'),
            'multa': Decimal('0'),
            'iof': Decimal('0'),
            'correcao': correcao,
            'status': 'paga' if paga else 'aberta',
        })

    return parcelas


def _parse_extrato_caixa_simulacao(texto_raw: str) -> dict[str, Any]:
    texto = _normalizar_texto(texto_raw)

    numero_contrato = _extrair_numero_contrato_caixa(texto_raw)
    aviso_extra = ''
    if not numero_contrato:
        m_emp = re.search(r'Empr[eé]stimo:\s*([\d.,]+)', texto_raw, flags=re.IGNORECASE)
        m_pz = re.search(r'Prazo\s+Total:\s*(\d+)\s*Meses', texto_raw, flags=re.IGNORECASE)
        if m_emp and m_pz:
            val = _dec(m_emp.group(1)).quantize(Decimal('0.01'))
            numero_contrato = f'CAIXA-{val}-{m_pz.group(1)}M'
            aviso_extra = (
                ' Número do contrato não veio no PDF; '
                f'usado identificador provisório {numero_contrato}. '
                'Ajuste no cadastro se necessário.'
            )
        else:
            raise ValueError('Número do contrato não encontrado no extrato Caixa.')

    cliente = ''
    m_empresa = re.search(r'Empresa:\s*(.+?)(?:\n|Taxa)', texto_raw, flags=re.IGNORECASE | re.S)
    if m_empresa:
        cliente = m_empresa.group(1).strip().strip('-').strip()

    valor_contrato = Decimal('0')
    for padrao in (
        r'Empr[eé]stimo:\s*([\d.,]+)',
        r'Total\s+Financiado:\s*([\d.,]+)',
    ):
        m_val = re.search(padrao, texto_raw, flags=re.IGNORECASE)
        if m_val:
            valor_contrato = _dec(m_val.group(1))
            break

    valor_tributos = Decimal('0')
    m_iof = re.search(r'IOF[^\d]*([\d.,]+)', texto_raw, flags=re.IGNORECASE)
    if m_iof:
        valor_tributos = _dec(m_iof.group(1))

    valor_tarifas = Decimal('0')
    m_tac = re.search(r'TAC[^\d]*([\d.,]+)', texto_raw, flags=re.IGNORECASE)
    if m_tac:
        valor_tarifas = _dec(m_tac.group(1))

    valor_servicos = Decimal('0')
    m_prest = re.search(r'Prestamista[^\d]*([\d.,]+)', texto_raw, flags=re.IGNORECASE)
    if m_prest:
        valor_servicos = _dec(m_prest.group(1))

    taxa_juros_am = Decimal('0')
    taxa_juros_aa = Decimal('0')
    m_tx = re.search(r'Taxa\s+de\s+Juros:\s*([\d.,]+)\s*%\s*am', texto_raw, flags=re.IGNORECASE)
    if m_tx:
        taxa_juros_am = _dec_pct(m_tx.group(1))
    m_cet = re.search(
        r'CET:\s*([\d.,]+)\s*%\s*am,\s*([\d.,]+)\s*%\s*aa',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_cet:
        taxa_juros_aa = _dec_pct(m_cet.group(2))

    prazo_parcelas = None
    m_pz = re.search(r'Prazo\s+Total:\s*(\d+)\s*Meses', texto_raw, flags=re.IGNORECASE)
    if m_pz:
        prazo_parcelas = int(m_pz.group(1))

    indicador_calculo, _, _, _ = normalizar_indicador_calculo('Price')
    modalidade = 'Empréstimo Caixa — Price/TR'
    if re.search(r'Price/TR', texto_raw, re.I):
        modalidade = 'Empréstimo Caixa — Price/TR'

    parcelas = _parse_parcelas_caixa_simulacao(texto_raw, data_referencia=date.today())
    if not parcelas:
        parcelas = _parse_parcelas_caixa_simulacao(texto, data_referencia=date.today())
    if not parcelas:
        raise ValueError('Nenhuma parcela encontrada no extrato Caixa.')

    qtd_pagas = sum(1 for p in parcelas if p['status'] == 'paga')
    qtd_abertas = len(parcelas) - qtd_pagas

    data_operacao = _parse_data(
        re.search(r'^0\s+(\d{2}/\d{2}/\d{4})', texto_raw, flags=re.MULTILINE).group(1)
    ) if re.search(r'^0\s+(\d{2}/\d{2}/\d{4})', texto_raw, flags=re.MULTILINE) else None
    data_vencimento = max(p['data_vencimento'] for p in parcelas)
    if not data_operacao:
        data_operacao = min(p['data_vencimento'] for p in parcelas)

    saldo_devedor_atualizado = Decimal('0')
    m_saldo_ini = re.search(
        r'^0\s+\d{2}/\d{2}/\d{4}\s+([\d.,]+)',
        texto_raw,
        flags=re.MULTILINE,
    )
    if m_saldo_ini:
        saldo_devedor_atualizado = _dec(m_saldo_ini.group(1))
    elif parcelas:
        saldo_devedor_atualizado = valor_contrato

    aviso = (
        f'Extrato Caixa (simulação Price/TR): {qtd_pagas} parcela(s) quitada(s) '
        f'(vencimento anterior a {date.today().strftime("%d/%m/%Y")}), '
        f'{qtd_abertas} em aberto.'
        + aviso_extra
    )

    return {
        'banco': 'caixa',
        'numero_contrato': str(numero_contrato).strip(),
        'cooperativa': '',
        'cliente': (cliente or '')[:250],
        'modalidade': modalidade[:200],
        'data_operacao': data_operacao,
        'data_vencimento': data_vencimento,
        'prazo_dias': None,
        'valor_contrato': valor_contrato or Decimal('0'),
        'valor_tributos': valor_tributos,
        'valor_tarifas': valor_tarifas,
        'valor_registros': Decimal('0'),
        'valor_servicos_terceiros': valor_servicos,
        'saldo_devedor_atualizado': saldo_devedor_atualizado or valor_contrato,
        'taxa_juros_am': taxa_juros_am or Decimal('0'),
        'taxa_juros_aa': taxa_juros_aa or Decimal('0'),
        'taxa_multa_am': Decimal('0'),
        'taxa_mora_am': Decimal('0'),
        'indice_correcao': 'TR',
        'indice_correcao_atraso': '',
        'pct_correcao_am': Decimal('0'),
        'pct_correcao_atraso_am': Decimal('0'),
        'indicador_calculo': indicador_calculo,
        'data_extrato': None,
        'parcelas': parcelas,
        'aviso': aviso,
        'prazo_parcelas': prazo_parcelas,
    }


def extrair_texto_caixa(file_obj) -> str:
    return extrair_texto_bradesco(file_obj)


def _normalizar_monetario_ocr(texto: str) -> str:
    """Corrige OCR como 16,.120,83 ou 392,.716,19."""
    t = texto or ''

    def _fix(m: re.Match) -> str:
        raw = m.group(0)
        digits = re.sub(r'[^\d]', '', raw)
        if len(digits) < 3:
            return raw
        inteiro, frac = digits[:-2], digits[-2:]
        inteiro_fmt = f'{int(inteiro):,}'.replace(',', '.') if inteiro else '0'
        return f'{inteiro_fmt},{frac}'

    t = re.sub(r'\d[\d.,]*,\.?\d[\d.,]*', _fix, t)
    t = re.sub(r'(\d),\.(\d{3},\d{2})', r'\1.\2', t)
    return t


def _normalizar_texto(texto: str) -> str:
    t = (texto or '').replace('\r', '\n')
    t = t.replace('RS ', 'R$ ')
    t = re.sub(r'[ \t]+', ' ', t)
    return t


def _parse_parcelas_caixa(texto: str, prazo_parcelas: int | None = None) -> list[dict[str, Any]]:
    """
    Linha principal (OCR):
      1 | 29/02/2024 16.120,83 | PARCELA DE 7.596,15 | PG 539.537,16 16.120,83
    Linhas seguintes:
      PARCELA DE JUROS 8.524,67 | PG
      JUROS PRO-RATA 747,82 | PG   (atraso — soma em mora / valor_pago)
    """
    linha_parc = re.compile(
        r'^(?P<num>\d{1,3})\s*[\)|\|]?\s*'
        r'(?P<venc>\d{2}/\d{2}/\d{4})\s+'
        r'(?P<parc>[\d.,]+)\s*\|\s*'
        r'PARCELA\s+DE\s+(?P<amort>[\d.,]+)\s*\|\s*'
        r'(?P<status>[A-Z]{2,12})\s+'
        r'(?P<saldo>[\d.,]+)\s+'
        r'(?P<pago>[\d.,]+)\s*$',
        flags=re.IGNORECASE,
    )
    linha_juros = re.compile(
        r'^PARCELA\s+DE\s+JUROS\s+(?P<juros>[\d.,]+)',
        flags=re.IGNORECASE,
    )
    linha_prorata = re.compile(
        r'^JUROS\s+PRO[- ]?RATA\s+(?P<valor>[\d.,]+)',
        flags=re.IGNORECASE,
    )

    linhas = [ln.strip() for ln in texto.replace('\r', '\n').splitlines() if ln.strip()]
    por_chave: dict[tuple[int, date], dict[str, Any]] = {}

    i = 0
    while i < len(linhas):
        ln = linhas[i]
        m = linha_parc.match(ln)
        if not m:
            i += 1
            continue

        num = int(m.group('num'))
        venc = _parse_data(m.group('venc'))
        if not venc or num < 1:
            i += 1
            continue

        valor_parcela = _dec(_normalizar_monetario_ocr(m.group('parc')))
        amortizacao = _dec(_normalizar_monetario_ocr(m.group('amort')))
        status_raw = (m.group('status') or '').upper()
        valor_pago = _dec(_normalizar_monetario_ocr(m.group('pago')))
        saldo = _dec(_normalizar_monetario_ocr(m.group('saldo')))

        juros = Decimal('0')
        mora = Decimal('0')
        hist_bits: list[str] = []

        j = i + 1
        while j < len(linhas):
            prox = linhas[j]
            if linha_parc.match(prox):
                break
            if re.match(
                r'^(Parc\s*\||Parc\.|Vencimento|Tipo|Modalidade|DADOS|CPF|Total|Data de|\. Valor)',
                prox,
                re.I,
            ):
                break
            if prox.upper() in ('AMORTIZACAO', 'ATRASO', 'ATRASO TOTAL'):
                j += 1
                continue
            mj = linha_juros.match(prox)
            if mj:
                juros = _dec(mj.group('juros'))
                j += 1
                continue
            mp = linha_prorata.match(prox)
            if mp:
                mora_val = _dec(mp.group('valor'))
                if mora_val > 0:
                    mora += mora_val
                    hist_bits.append(f'JUROS PRO-RATA {mp.group("valor")}')
                j += 1
                continue
            if prox.upper().startswith('PARCELA DE'):
                j += 1
                continue
            break

        paga = status_raw.startswith('PG')
        if juros <= 0 and valor_parcela > 0 and amortizacao > 0:
            juros = max(Decimal('0'), (valor_parcela - amortizacao).quantize(Decimal('0.01')))

        item = {
            'numero': num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': venc if paga else None,
            'historico': ' '.join(hist_bits)[:200],
            'valor_pago': valor_pago if paga else Decimal('0'),
            'mora': mora,
            'multa': Decimal('0'),
            'iof': Decimal('0'),
            'correcao': Decimal('0'),
            'status': 'paga' if paga else 'aberta',
            '_saldo': saldo,
            '_score': int(paga) + (1 if juros > 0 else 0) + (1 if mora > 0 else 0),
        }

        chave = (num, venc)
        ant = por_chave.get(chave)
        if ant is None or item['_score'] >= ant.get('_score', 0):
            por_chave[chave] = item

        i = j if j > i + 1 else i + 1

    parcelas = sorted(por_chave.values(), key=lambda r: (r['numero'], r['data_vencimento']))
    for r in parcelas:
        r.pop('_saldo', None)
        r.pop('_score', None)

    return parcelas


def parse_extrato_caixa(file_obj, texto_precalculado: str | None = None) -> dict[str, Any]:
    texto_raw = texto_precalculado or extrair_texto_caixa(file_obj)
    if not texto_raw.strip():
        raise ValueError(
            'Não foi possível ler o PDF da Caixa. '
            'Se for PDF em imagem, instale o Tesseract OCR (idioma português).'
        )
    if not parece_caixa(texto_raw):
        raise ValueError(
            'PDF não parece ser extrato ou demonstrativo de empréstimo da Caixa.'
        )

    if _eh_caixa_simulacao(texto_raw):
        return _parse_extrato_caixa_simulacao(texto_raw)

    texto = _normalizar_texto(texto_raw)
    linhas = [ln.strip() for ln in texto.replace('\r', '\n').splitlines() if ln.strip()]

    numero_contrato = _extrair_numero_contrato_caixa(texto_raw)
    if not numero_contrato:
        raise ValueError('Número do contrato não encontrado no PDF da Caixa.')

    cliente = ''
    m_nome = re.search(r'Nome:\s*(.+?)(?:\n|CPF)', texto_raw, flags=re.IGNORECASE)
    if m_nome:
        cliente = m_nome.group(1).strip()

    valor_contrato = Decimal('0')
    m_val = re.search(
        r'Valor\s+Contratado\s+([\d.,]+)',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_val:
        valor_contrato = _dec(m_val.group(1))

    saldo_devedor_atualizado = Decimal('0')
    m_sd = re.search(
        r'Saldo\s+Devedor\s+Atualizado\s+([\d.,]+)',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_sd:
        saldo_devedor_atualizado = _dec(m_sd.group(1))

    data_operacao = None
    m_op = re.search(
        r'Data\s+de\s+Contratac[aã]o\s+(\d{2}/\d{2}/\d{4})',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_op:
        data_operacao = _parse_data(m_op.group(1))

    data_vencimento = None
    m_uv = re.search(
        r'Data\s+Ultimo\s+vencimento\s+(\d{2}/\d{2}/\d{4})',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_uv:
        data_vencimento = _parse_data(m_uv.group(1))

    data_extrato = None
    m_em = re.search(
        r'Data\s+de\s+emiss[aã]o:\s*(\d{2}/\d{2}/\d{4})',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_em:
        data_extrato = _parse_data(m_em.group(1))

    taxa_juros_am = Decimal('0')
    taxa_juros_aa = Decimal('0')
    m_tx = re.search(
        r'Taxa\s+de\s+juros\s+contratada\s+([\d.,]+)',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_tx:
        taxa_juros_am = _dec_pct(m_tx.group(1))
    m_txa = re.search(
        r'Taxa\s+de\s+juros\s+anual\s+nominal\s+([\d.,]+)',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_txa:
        taxa_juros_aa = _dec_pct(m_txa.group(1))

    prazo_parcelas = None
    m_pz = re.search(
        r'Prazo\s+total\s*\(Meses\)\s+(\d{1,3})',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_pz:
        prazo_parcelas = int(m_pz.group(1))

    sistema = ''
    m_sys = re.search(
        r'Sistema\s+de\s+pagamento\s+(\w+)',
        texto_raw,
        flags=re.IGNORECASE,
    )
    if m_sys:
        sistema = m_sys.group(1).strip()
    indicador_calculo, _, _, _ = normalizar_indicador_calculo(sistema or 'PRICE')

    modalidade = 'BACEN 216'
    for ln in linhas:
        if re.search(r'Modalidade\s+BACEN', ln, re.I):
            modalidade = ln.strip()[:200]
            break

    parcelas = _parse_parcelas_caixa(texto, prazo_parcelas=prazo_parcelas)
    if not parcelas:
        parcelas = _parse_parcelas_caixa(texto_raw, prazo_parcelas=prazo_parcelas)
    if not parcelas:
        raise ValueError('Nenhuma parcela encontrada no PDF da Caixa.')

    if not data_vencimento and parcelas:
        data_vencimento = max(p['data_vencimento'] for p in parcelas)
    if not data_operacao and parcelas:
        data_operacao = min(p['data_vencimento'] for p in parcelas)

    aviso = None
    if prazo_parcelas and len(parcelas) < prazo_parcelas:
        aviso = (
            f'Prazo total no PDF: {prazo_parcelas} parcelas; '
            f'lidas {len(parcelas)} (o demonstrativo pode listar só parte das parcelas).'
        )

    return {
        'banco': 'caixa',
        'numero_contrato': str(numero_contrato).strip(),
        'cooperativa': '',
        'cliente': (cliente or '')[:250],
        'modalidade': modalidade[:200],
        'data_operacao': data_operacao,
        'data_vencimento': data_vencimento,
        'prazo_dias': None,
        'valor_contrato': valor_contrato or Decimal('0'),
        'valor_tributos': Decimal('0'),
        'valor_tarifas': Decimal('0'),
        'valor_registros': Decimal('0'),
        'valor_servicos_terceiros': Decimal('0'),
        'saldo_devedor_atualizado': saldo_devedor_atualizado or Decimal('0'),
        'taxa_juros_am': taxa_juros_am or Decimal('0'),
        'taxa_juros_aa': taxa_juros_aa or Decimal('0'),
        'taxa_multa_am': Decimal('0'),
        'taxa_mora_am': Decimal('0'),
        'indice_correcao': '',
        'indice_correcao_atraso': '',
        'pct_correcao_am': Decimal('0'),
        'pct_correcao_atraso_am': Decimal('0'),
        'indicador_calculo': indicador_calculo,
        'data_extrato': data_extrato,
        'parcelas': parcelas,
        'aviso': aviso,
        'prazo_parcelas': prazo_parcelas,
    }
