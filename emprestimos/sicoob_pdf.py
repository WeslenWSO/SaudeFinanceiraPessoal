"""
Parser do Extrato de Operação de Crédito Sicoob (SISBR).
Suporta Tabela Price e SAC Decrescente.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pdfplumber


def _dec(texto: str | None) -> Decimal:
    if not texto:
        return Decimal('0')
    t = str(texto).strip().replace('.', '').replace(',', '.')
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _dec_pct(texto: str | None) -> Decimal:
    """Percentuais: aceita 1,0000 (BR) e 0.19 (CET / ponto decimal)."""
    if not texto:
        return Decimal('0')
    t = str(texto).strip().replace('%', '').strip()
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _parse_data(texto: str | None, ano_completo: bool = False) -> date | None:
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


def normalizar_indicador_calculo(texto: str) -> tuple[str, int | None, str, str]:
    """
    Retorna (rotulo, codigo, nome, tipo).
    Exemplos: 15-Tabela Price | 3-Sac Decrescente | Tabela Price (Bradesco)
    """
    raw = (texto or '').strip()
    if not raw:
        return ('', None, '', 'outro')

    # Já no formato "N-Nome"
    m = re.match(r'^(\d+)\s*-\s*(.+)$', raw, flags=re.IGNORECASE)
    if m:
        codigo = int(m.group(1))
        nome = _expandir_nome_indicador(re.sub(r'\s+', ' ', m.group(2)).strip())
        rotulo = f'{codigo}-{nome}'
        tipo = _tipo_indicador(nome)
        return (rotulo[:100], codigo, nome[:80], tipo)

    # Só código
    m2 = re.match(r'^(\d+)$', raw)
    if m2:
        codigo = int(m2.group(1))
        return (str(codigo), codigo, str(codigo), 'outro')

    # Nome sem código (ex.: Bradesco "Tabela Price")
    nome = _expandir_nome_indicador(re.sub(r'\s+', ' ', raw))
    tipo = _tipo_indicador(nome)
    if tipo == 'price':
        return ('15-Tabela Price', 15, 'Tabela Price', 'price')
    if tipo == 'sac':
        return ('3-Sac Decrescente', 3, 'Sac Decrescente', 'sac')

    return (raw[:100], None, raw[:80], 'outro')


def _tipo_indicador(nome: str) -> str:
    n = (nome or '').lower()
    if 'price' in n or 'pric' in n:
        return 'price'
    if 'sac' in n:
        return 'sac'
    return 'outro'


def _expandir_nome_indicador(nome: str) -> str:
    """Normaliza abreviações do DDC (ex.: PRIC → Tabela Price)."""
    n = re.sub(r'\s+', ' ', (nome or '').strip())
    key = n.upper().replace(' ', '')
    mapa = {
        'TABELAPRICE': 'Tabela Price',
        'PRIC': 'Tabela Price',
        'PRICE': 'Tabela Price',
        'SAC': 'Sac Decrescente',
        'SACD': 'Sac Decrescente',
        'SACDECRESCENTE': 'Sac Decrescente',
    }
    return mapa.get(key, n)


def extrair_numero_contrato(texto: str) -> str | None:
    """
    Extrato: 'Número Contrato: 149.213'
    DDC:     'Contrato: 208695'
    Fallback: últimos dígitos do Número IPOC.
    """
    for padrao in (
        r'N[uú]mero\s+(?:do\s+)?Contrato:\s*([^\n]+)',
        r'(?m)^Contrato:\s*([\d.]+)\b',
        r'\bContrato:\s*([\d.]+)\b',
        r'N[uúº]?\s*Contrato\s+Modalidade\s*\n\s*(\d+)\b',
    ):
        m = re.search(padrao, texto, flags=re.IGNORECASE)
        if m:
            return re.sub(r'\s+', '', m.group(1).strip())

    m = re.search(r'N[uú]mero\s+IPOC:\s*(\d+)', texto, flags=re.IGNORECASE)
    if m:
        ipoc = m.group(1)
        if len(ipoc) >= 6:
            return ipoc[-6:].lstrip('0') or ipoc[-6:]
    return None


def extrair_indicador_do_texto(texto: str) -> str:
    """Extrai o indicador mesmo quando o PDF quebra em várias linhas."""
    # DDC: Indicador de Cálculo: 15-PRIC  |  Extrato: Indicador Cálculo: 15-Tabela Price
    m = re.search(
        r'Indicador\s+(?:de\s+)?C[aá]lculo:\s*(\d+\s*-\s*[^\n]+)',
        texto,
        flags=re.IGNORECASE,
    )
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()

    # Mesma linha legado
    m = re.search(r'Indicador C[aá]lculo:\s*(\d+\s*-\s*[^\n]+)', texto, flags=re.IGNORECASE)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()

    # Multilinha SAC: 3-Sac \n Indicador Cálculo: \n Decrescente
    m = re.search(
        r'(\d+\s*-\s*Sac)\s*\n\s*Indicador C[aá]lculo:\s*\n\s*(Decrescente|Crescente)',
        texto,
        flags=re.IGNORECASE,
    )
    if m:
        return f'{re.sub(r"\\s+", "", m.group(1))} {m.group(2).strip()}'

    # Código antes do rótulo e nome depois
    m = re.search(
        r'(\d+)\s*-\s*Sac\s+Indicador C[aá]lculo:\s*(Decrescente|Crescente)?',
        texto,
        flags=re.IGNORECASE,
    )
    if m:
        suf = (m.group(2) or 'Decrescente').strip()
        return f'{m.group(1)}-Sac {suf}'

    m = re.search(r'Indicador C[aá]lculo:\s*([^\n]+)', texto, flags=re.IGNORECASE)
    if m and m.group(1).strip() not in (':', ''):
        return re.sub(r'\s+', ' ', m.group(1)).strip()

    return ''


def extrair_texto_pdf(file_obj) -> str:
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    data = file_obj.read() if hasattr(file_obj, 'read') else file_obj
    if isinstance(data, str):
        data = data.encode('utf-8')
    partes: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            texto_pag = (
                page.extract_text(x_tolerance=2, y_tolerance=4)
                or page.extract_text()
                or ''
            )
            if texto_pag.strip():
                partes.append(texto_pag)
            # Tabelas (páginas seguintes do DDC costumam vir melhor assim)
            try:
                for table in page.extract_tables() or []:
                    for row in table or []:
                        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if cells:
                            partes.append(' '.join(cells))
            except Exception:
                pass
    texto = '\n'.join(partes)
    if not texto.strip():
        from .bradesco_pdf import extrair_texto_bradesco

        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        return extrair_texto_bradesco(file_obj)
    return texto


def _compactar_fluxo_ddc(texto: str) -> str:
    """
    Rejunta linhas quebradas do fluxo DDC (nº da parcela sozinho,
    histórico/valores na linha seguinte — comum nas páginas 2+).
    """
    linhas = [ln.strip() for ln in texto.replace('\r', '\n').split('\n')]
    out: list[str] = []
    for ln in linhas:
        if not ln:
            continue
        so_numero = re.fullmatch(r'\d{1,3}', ln)
        inicia_parcela = bool(re.match(r'^\d{1,3}\s+\d{2}/\d{2}/\d{4}', ln))
        if so_numero or inicia_parcela:
            out.append(ln)
            continue
        if out and (
            re.fullmatch(r'\d{1,3}', out[-1])
            or (
                re.match(r'^\d{1,3}\s+\d{2}/\d{2}/\d{4}', out[-1])
                and not re.search(r'[\d.]+,\d{2}.*[\d.]+,\d{2}.*[\d.]+,\d{2}', out[-1])
            )
        ):
            out[-1] = f'{out[-1]} {ln}'
        else:
            out.append(ln)
    return '\n'.join(out)


def parse_extrato_sicoob(file_obj) -> dict[str, Any]:
    """
    Retorna dict com cabeçalho do contrato e lista de parcelas.
    Parcela sem data de pagamento = aberta.

    Aceita Extrato de Operação de Crédito (com tabela de parcelas)
    e o DDC (Documento Descritivo do Crédito) com tabela Parc./Dt. Vcto.
    Lê todas as páginas do PDF.
    """
    texto = extrair_texto_pdf(file_obj)
    if not texto.strip():
        raise ValueError('Não foi possível extrair texto do PDF.')

    texto_upper = texto.upper()
    eh_ddc = 'DOCUMENTO DESCRITIVO' in texto_upper or ' DDC' in texto_upper or texto_upper.startswith('DDC')
    eh_extrato = 'EXTRATO DE OPERA' in texto_upper or 'NÚMERO CONTRATO' in texto_upper or 'NUMERO CONTRATO' in texto_upper
    eh_consulta = _eh_extrato_consulta(texto_upper)

    if 'SICOOB' not in texto_upper and not eh_extrato and not eh_ddc and not eh_consulta:
        if 'Contrato:' not in texto and 'Número Contrato' not in texto:
            raise ValueError('PDF não parece ser um Extrato/DDC de crédito Sicoob.')

    texto_nl = _compactar_fluxo_ddc(texto.replace('\r', '\n'))
    texto_norm = re.sub(r'[ \t]+', ' ', texto_nl)
    consulta = _parse_cabecalho_consulta(texto_nl, texto_norm) if eh_consulta else {}

    numero_contrato = extrair_numero_contrato(texto_norm) or extrair_numero_contrato(texto_nl)
    if not numero_contrato:
        raise ValueError(
            'Número do contrato não encontrado no PDF. '
            'No Extrato use "Número Contrato:"; no DDC o campo é "Contrato:".'
        )

    cooperativa = _campo(texto_norm, r'Cooperativa:\s*([^\n]+)') or consulta.get('cooperativa') or ''
    cliente = _campo(texto_norm, r'Cliente:\s*([^\n]+)') or consulta.get('cliente') or ''

    modalidade = _campo(texto_norm, r'Modalidade:\s*([^\n]+)') or consulta.get('modalidade') or ''
    if not modalidade or modalidade.strip() in (':',):
        m_mod = re.search(
            r'(\d{3,5}-Capital[^\n]*)\s*Modalidade:\s*([^\n]*)',
            texto_norm,
            flags=re.IGNORECASE,
        )
        if m_mod:
            modalidade = f'{m_mod.group(1).strip()} {m_mod.group(2).strip()}'.strip()
        else:
            m_giro = re.search(
                r'(\d{3,5}-CAPITAL DE GIRO[^\n*]*)',
                texto_norm,
                flags=re.IGNORECASE,
            )
            if m_giro:
                modalidade = m_giro.group(1).strip()
            else:
                m_giro2 = re.search(r'(Giro[^\n]*)', texto_norm, flags=re.IGNORECASE)
                if m_giro2:
                    modalidade = f'Capital de {m_giro2.group(1).strip()}'

    data_operacao = _parse_data(_campo(texto_norm, r'Data Opera[cç][aã]o:\s*(\d{2}/\d{2}/\d{4})')) or consulta.get('data_operacao')
    data_vencimento = (
        _parse_data(_campo(texto_norm, r'Data Vencimento:\s*(\d{2}/\d{2}/\d{4})'))
        or _parse_data(_campo(texto_norm, r'Data Vencto:\s*(\d{2}/\d{2}/\d{4})'))
        or consulta.get('data_vencimento')
    )
    data_extrato = (
        _parse_data(_campo(texto_norm, r'Data de Emiss[aã]o:\s*(\d{2}/\d{2}/\d{4})'))
        or _parse_data(_campo(texto_norm, r'Data:\s*(\d{2}/\d{2}/\d{4})'))
    )

    prazo_raw = (
        _campo(texto_norm, r'Prazo em dias:\s*([\d.]+)')
        or _campo(texto_norm, r'Prazo total:\s*([\d.]+)')
    )
    prazo_dias = int(prazo_raw.replace('.', '')) if prazo_raw else consulta.get('prazo_dias')

    valor_contrato = (
        _dec(_campo(texto_norm, r'Valor Contrato:\s*R\$\s*([\d.,]+)'))
        or _dec(_campo(texto_norm, r'Valor Contrato:\s*([\d.,]+)'))
        or _dec(_campo(texto_norm, r'Valor Opera[cç][aã]o:\s*R\$\s*([\d.,]+)'))
        or _dec(_campo(texto_norm, r'Valor Opera[cç][aã]o:\s*([\d.,]+)'))
        or consulta.get('valor_contrato')
        or Decimal('0')
    )

    # --- Taxas do extrato Sicoob (rótulos do DDC / Extrato) ---
    # Taxa Juros: 0,0000 % a.m.  (em CDI/SAC costuma ser 0 — correção pelo índice)
    taxa_juros_am = (
        _dec_pct(_campo(texto_norm, r'Taxa\s*Juros\s*\([^)]*\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Juros\s*\(a\.m\.\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Juros:\s*([\d.,]+)\s*%\s*a\.m'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Juros:\s*([\d.,]+)'))
        or consulta.get('taxa_juros_am')
        or Decimal('0')
    )
    # CET no fluxo (informativo): "CET 2.35 % a.a.CDI … 0.19 % a.m.CDI"
    cet_am = (
        _dec_pct(_campo(texto_norm, r'([\d.,]+)\s*%\s*a\.m\.?\s*CDI'))
        or _dec_pct(_campo(texto_nl, r'([\d.,]+)\s*%\s*a\.m\.?\s*CDI'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*de\s*Juros\s*([\d.,]+)\s*%\s*a\.m'))
    )
    cet_aa = (
        _dec_pct(_campo(texto_norm, r'CET\s*([\d.,]+)\s*%\s*a\.a\.?\s*CDI'))
        or _dec_pct(_campo(texto_nl, r'CET\s*([\d.,]+)\s*%\s*a\.a\.?\s*CDI'))
    )

    # Taxa Juros Anual: 0,0000
    taxa_juros_aa = (
        _dec_pct(_campo(texto_norm, r'Taxa\s*Juros\s*\(a\.a\.\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Juros\s*Anual:\s*([\d.,]+)'))
    )

    # Taxa Mora: 1,0000 % a.m.
    taxa_mora = (
        _dec_pct(_campo(texto_norm, r'Taxa\s*Mora\s*\(a\.m\.\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Mora:\s*([\d.,]+)\s*%\s*a\.m'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Mora:\s*([\d.,]+)'))
        or consulta.get('taxa_mora_am')
        or Decimal('0')
    )

    # Taxa Juros Inad.: 1,0000 % a.m.  (grava em taxa_multa_am)
    taxa_multa = (
        _dec_pct(_campo(texto_norm, r'Taxa\s*Juros\s*Inad\.?:\s*([\d.,]+)\s*%\s*a\.m'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Juros\s*Inad\.?:\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Multa\s*\(a\.m\.\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Multa:\s*([\d.,]+)\s*%\s*a\.m'))
        or _dec_pct(_campo(texto_norm, r'Taxa\s*Multa:\s*([\d.,]+)'))
        or consulta.get('taxa_multa_am')
        or Decimal('0')
    )

    # Índice Correção: CDI
    indice_correcao = (
        _campo(texto_norm, r'[IÍ]ndice\s*(?:de\s*)?Corre[cç][aã]o:\s*([A-Za-zÀ-ú]+)')
        or _campo(texto_norm, r'[IÍ]ndice\s*Corre[cç][aã]o:\s*([A-Za-zÀ-ú]+)')
        or ''
    )
    indice_correcao = re.sub(r'\s+', ' ', indice_correcao).strip()
    if indice_correcao.lower().startswith('atraso') or indice_correcao in (':', '-', '%'):
        indice_correcao = ''

    # Índice Correção Atraso: CDI
    indice_correcao_atraso = (
        _campo(texto_norm, r'[IÍ]ndice\s*(?:de\s*)?Corre[cç][aã]o\s*Atraso:\s*([A-Za-zÀ-ú]+)')
        or _campo(texto_norm, r'[IÍ]ndice\s*Cor\.?\s*Ats\.?:\s*([A-Za-zÀ-ú]+)')
        or ''
    )
    indice_correcao_atraso = re.sub(r'\s+', ' ', indice_correcao_atraso).strip()

    # % Índice: 192,00
    pct_correcao_am = (
        _dec_pct(_campo(texto_norm, r'%\s*[IÍ]ndice:\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'%\s*ndice:\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'%\s*de\s*Corre[cç][aã]o\s*\(a\.m\.\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_nl, r'%\s*[IÍ]ndice:\s*([\d.,]+)'))
    )
    # % Correção Atraso: 192,00
    pct_correcao_atraso_am = (
        _dec_pct(_campo(texto_norm, r'%\s*Corre[cç][aã]o\s*Atraso:\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_norm, r'%\s*de\s*Corre[cç][aã]o\s*Atraso\s*\(a\.m\.\):\s*([\d.,]+)'))
        or _dec_pct(_campo(texto_nl, r'%\s*Corre[cç][aã]o\s*Atraso:\s*([\d.,]+)'))
    )

    # Texto colado pelo pdfplumber: "CDI % Índice: 192,00"
    m_cdi = re.search(
        r'(?:^|[^\w])(CDI|SELIC|IPCA|IGPM?)\s*%\s*[IÍ]ndice:\s*([\d.,]+)',
        texto_norm,
        flags=re.IGNORECASE,
    )
    if m_cdi:
        if not indice_correcao:
            indice_correcao = m_cdi.group(1).strip().upper()
        if not pct_correcao_am:
            pct_correcao_am = _dec_pct(m_cdi.group(2))
    m_atr = re.search(
        r'(?:^|[^\w])(CDI|SELIC|IPCA|IGPM?)\s*%\s*Corre[cç][aã]o\s*Atraso:\s*([\d.,]+)',
        texto_norm,
        flags=re.IGNORECASE,
    )
    if m_atr:
        if not indice_correcao_atraso:
            indice_correcao_atraso = m_atr.group(1).strip().upper()
        if not pct_correcao_atraso_am:
            pct_correcao_atraso_am = _dec_pct(m_atr.group(2))

    # Se o índice veio com lixo ("CDI % Índice: 192,00"), separa
    m_lixo = re.match(
        r'^([A-Za-zÀ-ú]+)\s*%\s*[IÍ]ndice\s*:?\s*([\d.,]+)',
        indice_correcao or '',
        flags=re.IGNORECASE,
    )
    if m_lixo:
        indice_correcao = m_lixo.group(1).strip().upper()
        if not pct_correcao_am:
            pct_correcao_am = _dec_pct(m_lixo.group(2))

    if not indice_correcao and (pct_correcao_am or re.search(r'\bCDI\b', texto_norm, flags=re.IGNORECASE)):
        if re.search(r'\bCDI\b', texto_norm, flags=re.IGNORECASE):
            indice_correcao = 'CDI'
    if not indice_correcao_atraso and indice_correcao:
        indice_correcao_atraso = indice_correcao
    if not pct_correcao_atraso_am and pct_correcao_am:
        pct_correcao_atraso_am = pct_correcao_am

    # Sem CDI/% Índice (ex.: Price fixo): se Taxa Juros=0, usa CET a.m. quando houver
    tem_indice_flutuante = bool(pct_correcao_am) or (indice_correcao or '').upper() in (
        'CDI', 'SELIC', 'IPCA', 'IGP', 'IGPM',
    )
    if not taxa_juros_am and cet_am and not tem_indice_flutuante:
        taxa_juros_am = cet_am
    if not taxa_juros_aa and cet_aa and not tem_indice_flutuante:
        taxa_juros_aa = cet_aa
    indicador_raw = (
        extrair_indicador_do_texto(texto_nl)
        or extrair_indicador_do_texto(texto_norm)
        or consulta.get('indicador_calculo')
        or ''
    )
    rotulo, codigo, nome, tipo = normalizar_indicador_calculo(indicador_raw)

    parcelas_ext = _parse_parcelas_extrato(texto_norm, tipo=tipo, indice_correcao=indice_correcao)
    parcelas_consulta = _parse_parcelas_consulta(texto_norm) if eh_consulta else []
    parcelas_ddc = _parse_parcelas_ddc(texto_nl)
    if len(parcelas_ddc) < 2:
        parcelas_ddc2 = _parse_parcelas_ddc(texto_norm)
        if len(parcelas_ddc2) > len(parcelas_ddc):
            parcelas_ddc = parcelas_ddc2

    # Prefere o parse com melhor qualidade (pagas, amortização); desempate por qtd.
    parcelas = _escolher_melhor_parse_parcelas(parcelas_ext, parcelas_ddc)
    if parcelas_consulta:
        parcelas = _escolher_melhor_parse_parcelas(parcelas, parcelas_consulta)

    qtd_informada = (
        _campo(texto_norm, r'Qtd de Parcelas:\s*(\d+)')
        or _campo(texto_norm, r'Parcelas:\s*(\d+)')
    )
    qtd_esperada = int(qtd_informada) if qtd_informada and qtd_informada.isdigit() else None

    if not parcelas:
        raise ValueError(
            f'Contrato {numero_contrato} encontrado, mas nenhuma parcela foi lida. '
            'Confirme se o PDF traz a tabela (Parc. / Dt. Vcto. / Valor Parcela / Amortização).'
        )

    aviso = None
    if qtd_esperada and len(parcelas) < qtd_esperada:
        aviso = (
            f'Li apenas {len(parcelas)} parcela(s), mas o PDF informa {qtd_esperada}. '
            'Verifique se todas as páginas foram lidas; se persistir, coloque o PDF em '
            'emprestimos/samples/ para análise.'
        )

    parcelas.sort(key=lambda p: p['numero'])

    if tipo == 'sac' and taxa_juros_am > 0:
        from .sac_calculo import recalcular_sac_taxa_fixa_dicts

        parcelas = recalcular_sac_taxa_fixa_dicts(
            parcelas,
            valor_contrato=valor_contrato,
            taxa_juros_am=taxa_juros_am,
            taxa_mora_am=taxa_mora or Decimal('0'),
            data_operacao=data_operacao,
        )

    saldo_devedor_atualizado = (
        _dec(_campo(texto_norm, r'Saldo para Quita[cç][aã]o:\s*R\$\s*([\d.,]+)'))
        or _dec(_campo(texto_norm, r'Saldo para Quita[cç][aã]o:\s*([\d.,]+)'))
    )

    qtd_abertas_pdf = _campo(texto_norm, r'Parcelas em aberto:\s*(\d+)')
    if parcelas and any(p.get('numero') == 0 for p in parcelas):
        carencia = next(p for p in parcelas if p.get('numero') == 0)
        venc_c = carencia.get('data_vencimento')
        primeira_pag = next((p for p in parcelas if p.get('numero', 0) >= 1), None)
        if data_operacao and venc_c and primeira_pag:
            meses_c = max(0, (venc_c.year - data_operacao.year) * 12 + venc_c.month - data_operacao.month)
            hint_carencia = (
                f'Carência até {venc_c.strftime("%d/%m/%Y")} '
                f'({meses_c} meses após a operação). '
                f'1º pagamento: {primeira_pag["data_vencimento"].strftime("%d/%m/%Y")}.'
            )
            if aviso:
                aviso = f'{hint_carencia} {aviso}'
            else:
                aviso = hint_carencia

    return {
        'cooperativa': cooperativa[:200],
        'cliente': cliente[:250],
        'numero_contrato': numero_contrato.strip()[:40],
        'modalidade': modalidade[:200],
        'data_operacao': data_operacao,
        'data_vencimento': data_vencimento,
        'prazo_dias': prazo_dias,
        'valor_contrato': valor_contrato,
        'saldo_devedor_atualizado': saldo_devedor_atualizado,
        'taxa_juros_am': taxa_juros_am,
        'taxa_juros_aa': taxa_juros_aa,
        'taxa_multa_am': taxa_multa,
        'taxa_mora_am': taxa_mora,
        'indice_correcao': (indice_correcao or '')[:40],
        'indice_correcao_atraso': (indice_correcao_atraso or '')[:40],
        'pct_correcao_am': pct_correcao_am,
        'pct_correcao_atraso_am': pct_correcao_atraso_am,
        'indicador_calculo': rotulo or indicador_raw[:80],
        'indicador_codigo': codigo,
        'indicador_nome': nome,
        'indicador_tipo': tipo,
        'data_extrato': data_extrato,
        'parcelas': parcelas,
        'aviso': aviso,
        'qtd_parcelas_informada': qtd_esperada,
        'qtd_parcelas_abertas_pdf': int(qtd_abertas_pdf) if qtd_abertas_pdf and qtd_abertas_pdf.isdigit() else None,
    }


def _pontuacao_parse_parcelas(parcelas: list[dict[str, Any]]) -> tuple[int, int, float, int]:
    """
    Maior = melhor. Prioriza: qtd parcelas, pagas, amortização total, linhas com amort>0.
    """
    if not parcelas:
        return (0, 0, 0, 0)
    pagas = sum(1 for p in parcelas if p.get('status') == 'paga')
    amort_total = float(sum((p.get('amortizacao') or Decimal('0') for p in parcelas), Decimal('0')))
    com_amort = sum(1 for p in parcelas if (p.get('amortizacao') or Decimal('0')) > 0)
    return (len(parcelas), pagas, int(amort_total), com_amort)


def _escolher_melhor_parse_parcelas(
    parcelas_ext: list[dict[str, Any]],
    parcelas_ddc: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Escolhe extrato vs DDC pela qualidade (não só pela quantidade)."""
    if not parcelas_ext:
        return parcelas_ddc
    if not parcelas_ddc:
        return parcelas_ext
    score_ext = _pontuacao_parse_parcelas(parcelas_ext)
    score_ddc = _pontuacao_parse_parcelas(parcelas_ddc)
    if score_ext >= score_ddc:
        return parcelas_ext
    return parcelas_ddc


def _eh_extrato_consulta(texto_upper: str) -> bool:
    return (
        'CONSULTA DE EMPR' in texto_upper
        or 'EXTRATO DE OPERA' in texto_upper and 'CONSULTA' in texto_upper
        or 'VALOR DAPARCELA' in texto_upper
        or 'VALOR DA PARCELA' in texto_upper and 'PAGO' in texto_upper
    )


def _parse_cabecalho_consulta(texto_nl: str, texto_norm: str) -> dict[str, Any]:
    """Layout 'Consulta de empréstimos / Extrato de operações' (PDF em imagem)."""
    out: dict[str, Any] = {}

    m_cli = re.search(
        r'Cooperativa\s+Cliente\s*\n\s*(?P<linha>[^\n]+)',
        texto_nl,
        flags=re.IGNORECASE,
    )
    if m_cli:
        linha = m_cli.group('linha').strip()
        m_coop = re.match(r'(\d{4})', linha)
        if m_coop:
            out['cooperativa'] = m_coop.group(1)
        m_conta = re.search(r'(\d{4,6}-\d\s+.+)', linha)
        if m_conta:
            out['cliente'] = m_conta.group(1).strip()[:250]
        elif 'LTDA' in linha.upper():
            out['cliente'] = linha[:250]

    m_mod = re.search(
        r'N[uúº]?\s*Contrato\s+Modalidade\s*\n\s*\d+\s+([^\n]+(?:\n[^\n]+)?)',
        texto_nl,
        flags=re.IGNORECASE,
    )
    if m_mod:
        modalidade = re.sub(r'\s+', ' ', m_mod.group(1)).strip()
        out['modalidade'] = modalidade[:200]

    m_datas = re.search(
        r'Data da opera[cç][aã]o\s+Vencimento\s*\n\s*'
        r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})',
        texto_norm,
        flags=re.IGNORECASE,
    )
    if m_datas:
        out['data_operacao'] = _parse_data(m_datas.group(1))
        out['data_vencimento'] = _parse_data(m_datas.group(2))

    m_prazo = re.search(
        r'Prazo\s+Valor do contrato\s*\n\s*(\d+)\s*dias\s*(?:R\$|RS)\s*([\d.,]+)',
        texto_norm,
        flags=re.IGNORECASE,
    )
    if m_prazo:
        out['prazo_dias'] = int(m_prazo.group(1))
        out['valor_contrato'] = _dec(m_prazo.group(2))

    m_taxas = re.search(
        r'Taxa de Juros\s+Taxa de Mora\s*\n\s*([\d.,]+)\s*%\s*([\d.,]+)\s*%',
        texto_norm,
        flags=re.IGNORECASE,
    )
    if m_taxas:
        out['taxa_juros_am'] = _dec_pct(m_taxas.group(1))
        out['taxa_mora_am'] = _dec_pct(m_taxas.group(2))

    m_multa = re.search(
        r'Taxa de Multa\s+Indicador[^\n]*\n\s*([\d.,]+)\s*%\s*(\d+\s*-\s*[^\n]+)',
        texto_norm,
        flags=re.IGNORECASE,
    )
    if m_multa:
        out['taxa_multa_am'] = _dec_pct(m_multa.group(1))
        out['indicador_calculo'] = re.sub(r'\s+', ' ', m_multa.group(2)).strip()

    return out


def _parse_parcelas_consulta(texto_norm: str) -> list[dict[str, Any]]:
    """
    Extrato Consulta Sicoob (imagem):
      1 10/03/2025 R$ 12.053,82 Sim
      18 10/08/2026 R$ 12.053,82 -
    """
    parcela_re = re.compile(
        r'(?m)^(?P<num>\d{1,3})\s+'
        r'(?P<venc>\d{2}/\d{2}/\d{4})\s+'
        r'(?:R\$|RS)\s*(?P<parc>[\d.,]+)\s+'
        r'(?P<pago>Sim|=|-=?)'
        r'\s*$',
        flags=re.IGNORECASE,
    )
    por_num: dict[int, dict[str, Any]] = {}
    for m in parcela_re.finditer(texto_norm):
        num = int(m.group('num'))
        if num > 600:
            continue
        venc = _parse_data(m.group('venc'))
        if not venc:
            continue
        valor_parcela = _dec(m.group('parc'))
        pago = (m.group('pago') or '').strip().lower().startswith('sim')
        row = {
            'numero': num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': valor_parcela,
            'juros': Decimal('0'),
            'data_pagamento': venc if pago else None,
            'historico': '',
            'valor_pago': valor_parcela if pago else None,
            'mora': Decimal('0'),
            'multa': Decimal('0'),
            'iof': Decimal('0'),
            'correcao': Decimal('0'),
            'status': 'paga' if pago else 'aberta',
        }
        ant = por_num.get(num)
        if ant is None or (pago and ant.get('status') != 'paga'):
            por_num[num] = row
    return list(por_num.values())


def _parse_parcelas_extrato(
    texto_norm: str,
    *,
    tipo: str,
    indice_correcao: str,
) -> list[dict[str, Any]]:
    """Formato Extrato: N venc parc amort juros [pagamento] ..."""
    _money = r'(?:R\$\s*)?[\d.]+,\d{2}'
    parcela_re = re.compile(
        r'(?m)^(?P<num>\d+)\s+'
        r'(?P<venc>\d{2}/\d{2}/\d{2,4})\s+'
        rf'(?P<parc>{_money})\s+'
        rf'(?P<amort>{_money})'
        rf'(?:\s+(?P<juros_or_extra>{_money}|\d{{2}}/\d{{2}}/\d{{2,4}}|-))?'
        rf'(?:\s+(?P<pag_extra>\d{{2}}/\d{{2}}/\d{{2,4}}|-))?'
        r'(?P<resto>.*)$'
    )

    parcelas: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for m in parcela_re.finditer(texto_norm):
        num = int(m.group('num'))
        if num in vistos or num > 600:
            continue
        vistos.add(num)

        venc = _parse_data(m.group('venc'))
        if not venc:
            continue

        parc_raw = m.group('parc')
        amort_raw = m.group('amort')
        valor_parcela = _dec(re.sub(r'^R\$\s*', '', parc_raw))
        amortizacao = _dec(re.sub(r'^R\$\s*', '', amort_raw))

        juros = Decimal('0')
        data_pag = None
        juros_or_extra = (m.group('juros_or_extra') or '').strip()
        pag_extra = (m.group('pag_extra') or '').strip()
        resto = (m.group('resto') or '').strip()

        if juros_or_extra and re.match(rf'^{_money}$', juros_or_extra):
            juros = _dec(re.sub(r'^R\$\s*', '', juros_or_extra))
        elif juros_or_extra and re.match(r'\d{2}/\d{2}/\d{2,4}', juros_or_extra):
            data_pag = _parse_data(juros_or_extra)
        elif juros_or_extra == '-':
            pass

        if pag_extra and re.match(r'\d{2}/\d{2}/\d{2,4}', pag_extra):
            data_pag = _parse_data(pag_extra)

        # SAC "operação em aberto": parcela R$ 0,00 e amortização preenchida
        if valor_parcela <= 0 and amortizacao > 0:
            valor_parcela = (amortizacao + juros).quantize(Decimal('0.01'))
        elif valor_parcela > 0 and amortizacao <= 0 and juros <= 0:
            amortizacao = max(
                Decimal('0'),
                (valor_parcela - juros).quantize(Decimal('0.01')),
            )

        if valor_parcela <= 0 and amortizacao <= 0 and juros <= 0:
            if num == 0:
                parcelas.append({
                    'numero': num,
                    'data_vencimento': venc,
                    'valor_parcela': Decimal('0.00'),
                    'amortizacao': Decimal('0.00'),
                    'juros': Decimal('0.00'),
                    'data_pagamento': None,
                    'historico': 'Carência',
                    'valor_pago': None,
                    'mora': Decimal('0'),
                    'iof': Decimal('0'),
                    'correcao': Decimal('0'),
                    'status': 'aberta',
                })
            continue

        historico = ''
        valor_pago = None
        mora = Decimal('0')
        iof = Decimal('0')
        correcao = Decimal('0')

        if data_pag:
            moneys = re.findall(r'(?:R\$\s*)?[\d.]+,\d{2}', resto)
            hist_bits = re.findall(r'[A-Za-zÀ-ú/]+', resto)
            historico = ' '.join(hist_bits[:8]).strip()
            if moneys:
                valor_pago = _dec(re.sub(r'^R\$\s*', '', moneys[0]))
            if len(moneys) >= 2:
                if tipo == 'sac' or 'corre' in historico.lower() or indice_correcao:
                    correcao = _dec(re.sub(r'^R\$\s*', '', moneys[1]))
                else:
                    mora = _dec(re.sub(r'^R\$\s*', '', moneys[1]))
            if len(moneys) >= 3:
                iof = _dec(re.sub(r'^R\$\s*', '', moneys[2]))
        elif resto.startswith('-') or ' - ' in resto:
            data_pag = None

        parcelas.append({
            'numero': num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': data_pag,
            'historico': historico[:200],
            'valor_pago': valor_pago,
            'mora': mora,
            'iof': iof,
            'correcao': correcao,
            'status': 'paga' if data_pag else 'aberta',
        })
    return parcelas


def _interpretar_colunas_aberto(vals: list[str], valor_parcela: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """
    Mapeia colunas de parcela em aberto (DDC Sicoob).

    Layouts comuns na extração do PDF:
      A) parcela | correção | juros | …
      B) parcela | juros | …           (sem coluna correção — frequente no PDF)
      C) parcela | amort | juros       (formato legado)
    """
    col = [_dec(x) for x in vals[1:]]
    while len(col) < 3:
        col.append(Decimal('0'))

    correcao = Decimal('0')
    juros = Decimal('0')
    amortizacao = Decimal('0')
    c1, c2, c3 = col[0], col[1], col[2]

    # SAC extrato em aberto: parcela zerada, amortização na 2ª coluna
    if valor_parcela <= 0 and c2 > 0:
        amortizacao = c2
        juros = c3 if c3 > 0 else Decimal('0')
        return correcao, juros, amortizacao

    # Layout A: correção (geralmente 0) + juros na 3ª coluna
    if c2 > 0 and c2 < valor_parcela and (c1 == 0 or c1 <= c2):
        correcao = c1
        juros = c2
    # Layout B: juros na 2ª coluna (PDF omite coluna correção)
    elif c1 > 0 and c1 < valor_parcela and c2 == 0:
        juros = c1
    # Layout C legado: amort explícita na 2ª coluna
    elif c1 > 0 and c1 < valor_parcela:
        if c2 > 0 and abs((c1 + c2) - valor_parcela) <= Decimal('0.05'):
            amortizacao = c1
            juros = c2
        elif c2 == 0:
            amortizacao = c1

    if amortizacao <= 0:
        amortizacao = max(
            Decimal('0'),
            (valor_parcela - juros - correcao).quantize(Decimal('0.01')),
        )
    return correcao, juros, amortizacao


def _parse_parcelas_ddc(texto: str) -> list[dict[str, Any]]:
    """
    Formato DDC (tabela Parc. / Dt. Vcto. / Dt. Pagto / ...):

    Paga:
    1 03/02/2025 03/02/2025 DEBITO AUTOMATICO EM C/C S 17.051,19 17.051,19 4.651,62 12.399,57 0,00 0,00 0,00

    Em aberto (Dt. Pagto='-', Liq=N) — formato antigo com amortização:
    19 03/08/2026 - N 0 17.051,19 0,00 0,00

    Em aberto (sem Dt. Pagto; Dias Atraso + Valor Parcela + Correção + Juros):
    32 03/08/2026 0 67.828,07 0,00 35.761,39 0,00 0,00 0,00 0,00
    """
    linha_re = re.compile(
        r'(?m)^(?P<num>\d{1,3})\s+'
        r'(?P<venc>\d{2}/\d{2}/\d{4})'
        r'(?:\s+(?P<pag>\d{2}/\d{2}/\d{4}|-))?'
        r'\s+(?P<resto>.+)$'
    )

    brutos: list[dict[str, Any]] = []
    for m in linha_re.finditer(texto):
        num = int(m.group('num'))
        if num < 1 or num > 600:
            continue
        venc = _parse_data(m.group('venc'))
        if not venc:
            continue

        resto = (m.group('resto') or '').strip()
        if re.search(
            r'Valor Parcela|Amortiza|Dt\.?\s*Vcto|Hist[oó]rico|CET|Custo Efetivo|Evolu[cç][aã]o do Saldo|Dias de Atraso',
            resto,
            re.I,
        ):
            continue

        pag_raw = (m.group('pag') or '').strip()
        data_pag = None if pag_raw in ('', '-') else _parse_data(pag_raw)

        liquidada = bool(re.search(r'(?:^|\s)S(?:\s|$)', resto))
        nao_liquidada = bool(re.search(r'(?:^|\s)N(?:\s|$)', resto))

        blocos = list(re.finditer(r'(?:R\$\s*)?[\d.]+,\d{2}', resto))

        em_aberto = (
            (not data_pag and not liquidada)
            or nao_liquidada
            or pag_raw == '-'
        )

        min_blocos = 2 if em_aberto else 3
        if len(blocos) < min_blocos:
            continue

        # Em aberto (sem data de pagamento / não liquidada):
        # PDF recente: Valor Parcela | Valor Correção | Valor Juros | …
        # Não usar o mapeamento de 7 colunas das liquidadas.

        if em_aberto:
            vals = [re.sub(r'^R\$\s*', '', x.group(0)) for x in blocos]
            valor_pago = Decimal('0')
            valor_parcela = _dec(vals[0])
            correcao, juros, amortizacao = _interpretar_colunas_aberto(vals, valor_parcela)
            if valor_parcela <= 0 and amortizacao > 0:
                valor_parcela = (amortizacao + juros + correcao).quantize(Decimal('0.01'))
            mora = _dec(vals[3]) if len(vals) > 3 else Decimal('0')
            iof = _dec(vals[6]) if len(vals) > 6 else Decimal('0')
            money_matches = blocos
        elif len(blocos) >= 7:
            money_matches = blocos[-7:]
            vals = [x.group(0) for x in money_matches]
            valor_pago = _dec(vals[0])
            valor_parcela = _dec(vals[1])
            amortizacao = _dec(vals[2])
            juros = _dec(vals[3])
            mora = _dec(vals[4])
            iof = _dec(vals[6])
            correcao = Decimal('0')
        elif len(blocos) >= 5:
            money_matches = blocos[-min(7, len(blocos)):]
            vals = [x.group(0) for x in money_matches]
            while len(vals) < 7:
                vals.append('0,00')
            valor_pago = _dec(vals[0])
            valor_parcela = _dec(vals[1])
            amortizacao = _dec(vals[2])
            juros = _dec(vals[3])
            mora = _dec(vals[4])
            iof = _dec(vals[6]) if len(vals) > 6 else Decimal('0')
            correcao = Decimal('0')
        else:
            money_matches = blocos[-3:]
            vals = [x.group(0) for x in money_matches]
            valor_pago = Decimal('0')
            valor_parcela = _dec(vals[0])
            amortizacao = _dec(vals[1])
            juros = _dec(vals[2])
            mora = Decimal('0')
            iof = Decimal('0')
            correcao = Decimal('0')

        if valor_parcela <= 0 and amortizacao <= 0 and juros <= 0:
            continue

        prefixo = resto[: money_matches[0].start()].strip()
        historico = re.sub(r'\s+[SN](?:\s+\d+)?\s*$', '', prefixo).strip()
        historico = re.sub(r'^[SN](?:\s+\d+)?\s*', '', historico).strip()
        historico = re.sub(r'^-\s*', '', historico)
        historico = re.sub(r'\s+', ' ', historico)
        if re.fullmatch(r'[SN](?:\s+\d+)?', historico or ''):
            historico = ''

        if liquidada or (valor_pago > 0 and valor_parcela > 0 and valor_pago >= valor_parcela):
            status = 'paga'
        elif em_aberto:
            status = 'aberta'
        else:
            status = 'aberta'

        brutos.append({
            'numero': num,
            'data_vencimento': venc,
            'valor_parcela': valor_parcela,
            'amortizacao': amortizacao,
            'juros': juros,
            'data_pagamento': data_pag,
            'historico': historico[:200],
            'valor_pago': valor_pago if valor_pago > 0 else None,
            'mora': mora,
            'iof': iof,
            'correcao': correcao,
            'status': status,
            'liquidada': liquidada,
        })

    return _agregar_linhas_parcela(brutos)


def _agregar_linhas_parcela(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Junta pagamentos parciais da mesma parcela em um único registro."""
    ordem: list[int] = []
    acc: dict[int, dict[str, Any]] = {}

    for row in linhas:
        n = row['numero']
        if n not in acc:
            ordem.append(n)
            item = {k: v for k, v in row.items() if k != 'liquidada'}
            acc[n] = item
            if row.get('liquidada'):
                acc[n]['status'] = 'paga'
            continue

        cur = acc[n]
        # Amort/juros da parcela se repetem nas linhas parciais — usa o maior
        cur['amortizacao'] = max(cur['amortizacao'], row['amortizacao'])
        cur['juros'] = max(cur['juros'], row['juros'])
        cur['mora'] += row['mora']
        cur['iof'] += row['iof']
        cur['valor_parcela'] = max(cur['valor_parcela'], row['valor_parcela'])

        vp = row.get('valor_pago') or Decimal('0')
        if vp:
            cur['valor_pago'] = (cur.get('valor_pago') or Decimal('0')) + vp

        if row.get('data_pagamento'):
            if (
                not cur.get('data_pagamento')
                or row['data_pagamento'] >= cur['data_pagamento']
            ):
                cur['data_pagamento'] = row['data_pagamento']

        hist = (row.get('historico') or '').strip()
        if hist:
            if 'LIQUID' in hist.upper() or not cur.get('historico'):
                cur['historico'] = hist[:200]
            elif hist.upper() not in (cur.get('historico') or '').upper():
                cur['historico'] = f"{cur['historico']}; {hist}"[:200]

        if row.get('liquidada'):
            cur['status'] = 'paga'

    for cur in acc.values():
        if cur['status'] == 'aberta':
            vp = cur.get('valor_pago') or Decimal('0')
            if cur['valor_parcela'] > 0 and vp >= cur['valor_parcela']:
                cur['status'] = 'paga'

    return [acc[n] for n in ordem]
