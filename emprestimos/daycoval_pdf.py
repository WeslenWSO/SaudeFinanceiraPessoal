"""
Parser do Fluxo Financeiro da Operação (Daycoval Leasing / Autbank).

Colunas: Parcela | Vencimento | Tipo | Principal | Juros | Impostos | Valor Nominal | Saldo
Importa linhas PARCELA e RESIDUAL (VRG), numeradas em ordem cronológica.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

import pdfplumber

from .bradesco_pdf import extrair_texto_bradesco
from .sicoob_pdf import _dec, _dec_pct, _parse_data, normalizar_indicador_calculo


def parece_daycoval(texto: str) -> bool:
    u = (texto or '').upper()
    return (
        'DAYCOVAL' in u
        and (
            'FLUXO FINANCEIRO' in u
            or 'AUTBANK LEASING' in u
            or 'RLEFLXFI' in u
        )
    )


def extrair_texto_daycoval(file_obj) -> str:
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    with pdfplumber.open(file_obj) as pdf:
        texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)
    if texto.strip():
        return texto
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    return extrair_texto_bradesco(file_obj)


def _taxa_am_de_aa(taxa_aa: Decimal) -> Decimal:
    if taxa_aa <= 0:
        return Decimal('0')
    fator = (Decimal('1') + taxa_aa / Decimal('100')) ** (Decimal('1') / Decimal('12'))
    return ((fator - Decimal('1')) * Decimal('100')).quantize(Decimal('0.0001'))


def _parse_parcelas_daycoval(
    texto: str,
    data_referencia: date | None = None,
) -> list[dict[str, Any]]:
    linha_re = re.compile(
        r'^(?P<num>\d{1,3})\s+'
        r'(?P<venc>\d{2}/\d{2}/\d{4})\s+'
        r'(?P<tipo>PARCELA|RESIDUAL)\s+'
        r'(?P<principal>[\d.,]+)\s+'
        r'(?P<juros>[\d.,]+)\s+'
        r'(?P<impostos>[\d.,]+)\s+'
        r'(?P<nominal>[\d.,]+)\s+'
        r'(?P<saldo>[\d.,]+)\s*$',
        flags=re.IGNORECASE | re.MULTILINE,
    )

    por_chave: dict[tuple[date, str], dict[str, Any]] = {}
    for m in linha_re.finditer(texto):
        tipo = m.group('tipo').upper()
        pdf_num = int(m.group('num'))
        venc = _parse_data(m.group('venc'))
        if not venc:
            continue

        amortizacao = _dec(m.group('principal'))
        juros = _dec(m.group('juros'))
        impostos = _dec(m.group('impostos'))
        valor_parcela = _dec(m.group('nominal'))
        saldo = _dec(m.group('saldo'))

        if tipo == 'RESIDUAL':
            historico = f'RESIDUAL VRG ref. {pdf_num} Daycoval Leasing'
        else:
            historico = f'PARCELA ref. {pdf_num} Daycoval Leasing'

        paga = bool(data_referencia and venc < data_referencia)
        item = {
            'tipo_fluxo': tipo,
            'pdf_num': pdf_num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': venc if paga else None,
            'historico': historico,
            'valor_pago': valor_parcela if paga else Decimal('0'),
            'mora': Decimal('0'),
            'multa': Decimal('0'),
            'iof': impostos,
            'correcao': Decimal('0'),
            'status': 'paga' if paga else 'aberta',
            '_saldo': saldo,
            '_score': int(tipo == 'PARCELA'),
        }

        chave = (venc, tipo)
        ant = por_chave.get(chave)
        if ant is None or item['_score'] >= ant.get('_score', 0):
            por_chave[chave] = item

    ordenadas = sorted(
        por_chave.values(),
        key=lambda r: (r['data_vencimento'], 0 if r['tipo_fluxo'] == 'RESIDUAL' else 1),
    )
    parcelas: list[dict[str, Any]] = []
    for i, row in enumerate(ordenadas, start=1):
        item = dict(row)
        item['numero'] = i
        item.pop('_score', None)
        parcelas.append(item)
    return parcelas


def parse_extrato_daycoval(file_obj, texto_precalculado: str | None = None) -> dict[str, Any]:
    texto_raw = texto_precalculado or extrair_texto_daycoval(file_obj)
    if not texto_raw.strip():
        raise ValueError(
            'Não foi possível ler o PDF Daycoval. '
            'Se for PDF em imagem, instale o Tesseract OCR (idioma português).'
        )
    if not parece_daycoval(texto_raw):
        raise ValueError('PDF não parece ser o Fluxo Financeiro Daycoval Leasing.')

    texto = texto_raw.replace('\r', '\n')

    m_op = re.search(
        r'Opera[cç][aã]o:\s*(\S+)\s+(.+?)\s+Garantia:',
        texto,
        flags=re.IGNORECASE | re.S,
    )
    if not m_op:
        raise ValueError('Número da operação não encontrado no PDF Daycoval.')
    numero_contrato = m_op.group(1).strip()
    cliente = re.sub(r'\s+', ' ', m_op.group(2)).strip()

    data_operacao = _parse_data(
        re.search(r'In[ií]cio:\s*(\d{2}/\d{2}/\d{4})', texto, re.I).group(1)
        if re.search(r'In[ií]cio:\s*(\d{2}/\d{2}/\d{4})', texto, re.I)
        else None
    )
    data_vencimento = _parse_data(
        re.search(r'Vencimento:\s*(\d{2}/\d{2}/\d{4})', texto, re.I).group(1)
        if re.search(r'Vencimento:\s*(\d{2}/\d{2}/\d{4})', texto, re.I)
        else None
    )

    data_extrato = None
    m_em = re.search(r'Emiss[aã]o:\s*(\d{2}/\d{2}/\d{4})', texto, flags=re.I)
    if m_em:
        data_extrato = _parse_data(m_em.group(1))

    valor_contrato = Decimal('0')
    m_val = re.search(r'Valor\s+Opera[cç][aã]o:\s*([\d.,]+)', texto, flags=re.I)
    if m_val:
        valor_contrato = _dec(m_val.group(1))

    saldo_devedor_atualizado = Decimal('0')
    linha_re = re.compile(
        r'^(?P<num>\d{1,3})\s+(?P<venc>\d{2}/\d{2}/\d{4})\s+PARCELA\s+'
        r'[\d.,]+\s+[\d.,]+\s+[\d.,]+\s+[\d.,]+\s+(?P<saldo>[\d.,]+)\s*$',
        flags=re.I | re.M,
    )
    if data_extrato:
        ultimo_saldo = None
        for m in linha_re.finditer(texto):
            venc = _parse_data(m.group('venc'))
            if venc and venc < data_extrato:
                ultimo_saldo = _dec(m.group('saldo'))
        if ultimo_saldo is not None:
            saldo_devedor_atualizado = ultimo_saldo

    taxa_raw = Decimal('0')
    m_tx = re.search(r'Taxa\s+Opera[cç][aã]o:\s*([\d.,]+)', texto, flags=re.I)
    if m_tx:
        taxa_raw = _dec_pct(m_tx.group(1))

    taxa_juros_aa = Decimal('0')
    taxa_juros_am = Decimal('0')
    if taxa_raw > Decimal('5'):
        taxa_juros_aa = taxa_raw
        taxa_juros_am = _taxa_am_de_aa(taxa_raw)
    elif taxa_raw > 0:
        taxa_juros_am = taxa_raw
        taxa_juros_aa = (taxa_raw * Decimal('12')).quantize(Decimal('0.0001'))

    modalidade = 'DAYCOVAL LEASING'
    if 'AUTBANK LEASING' in texto.upper():
        modalidade = 'DAYCOVAL LEASING — AUTBANK'

    indicador_calculo, _, _, _ = normalizar_indicador_calculo('Sac Decrescente')

    parcelas = _parse_parcelas_daycoval(texto, data_referencia=data_extrato)
    if not parcelas:
        raise ValueError('Nenhuma linha PARCELA/RESIDUAL encontrada no PDF Daycoval.')

    parcelas_price = [p for p in parcelas if p['tipo_fluxo'] == 'PARCELA']
    parcelas_residual = [p for p in parcelas if p['tipo_fluxo'] == 'RESIDUAL']

    if not data_vencimento:
        data_vencimento = max(p['data_vencimento'] for p in parcelas)
    if not data_operacao:
        data_operacao = min(p['data_vencimento'] for p in parcelas)
    if not saldo_devedor_atualizado:
        pagas = [p for p in parcelas_price if p['status'] == 'paga']
        if pagas:
            ultima = max(pagas, key=lambda p: p['data_vencimento'])
            saldo_devedor_atualizado = ultima.get('_saldo') or Decimal('0')

    for r in parcelas:
        r.pop('_saldo', None)

    prazo_parcelas = len(parcelas_price)
    qtd_abertas = sum(1 for p in parcelas if p['status'] == 'aberta')

    aviso = (
        f'Daycoval Leasing: {len(parcelas_price)} parcela(s) e '
        f'{len(parcelas_residual)} residual(is) VRG importados. '
    )
    if data_extrato:
        aviso += (
            f'Status estimado pela emissão ({data_extrato.strftime("%d/%m/%Y")}): '
            f'{qtd_abertas} em aberto.'
        )

    return {
        'banco': 'daycoval',
        'numero_contrato': numero_contrato,
        'cooperativa': '',
        'cliente': cliente[:250],
        'modalidade': modalidade[:200],
        'data_operacao': data_operacao,
        'data_vencimento': data_vencimento,
        'prazo_dias': None,
        'valor_contrato': valor_contrato,
        'valor_tributos': Decimal('0'),
        'valor_tarifas': Decimal('0'),
        'valor_registros': Decimal('0'),
        'valor_servicos_terceiros': Decimal('0'),
        'saldo_devedor_atualizado': saldo_devedor_atualizado,
        'taxa_juros_am': taxa_juros_am,
        'taxa_juros_aa': taxa_juros_aa,
        'taxa_multa_am': Decimal('0'),
        'taxa_mora_am': Decimal('0'),
        'indice_correcao': 'REAL',
        'indice_correcao_atraso': '',
        'pct_correcao_am': Decimal('0'),
        'pct_correcao_atraso_am': Decimal('0'),
        'indicador_calculo': indicador_calculo,
        'data_extrato': data_extrato,
        'parcelas': parcelas,
        'aviso': aviso,
        'prazo_parcelas': prazo_parcelas,
    }
