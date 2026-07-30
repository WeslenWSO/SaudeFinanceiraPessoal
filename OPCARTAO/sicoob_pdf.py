"""Parser de fatura de cartão de crédito Sicoob (PDF)."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from .categorias import inferir_categoria

_RE_VALOR_FIM = re.compile(r'(-?\d{1,3}(?:\.\d{3})*,\d{2})$')
_RE_DATA_INICIO = re.compile(r'^(\d{2}/\d{2})\s+')
_RE_DATA_VALOR = re.compile(r'^(\d{2}/\d{2})\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})$')
_RE_PARCELA = re.compile(r'\b(\d{2}/\d{2})\b')
_RE_FINAL_CARTAO = re.compile(r'^\((\d{4})\)$')


def _fold(s: str) -> str:
    if not s:
        return ''
    d = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in d if unicodedata.category(c) != 'Mn').lower()


def _parse_moeda(txt: str) -> Decimal:
    s = (txt or '').replace('R$', '').replace(' ', '').strip()
    if not s:
        return Decimal('0')
    neg = s.startswith('-')
    s = s.lstrip('-')
    s = s.replace('.', '').replace(',', '.')
    try:
        val = Decimal(s).quantize(Decimal('0.01'))
        return -val if neg else val
    except InvalidOperation:
        return Decimal('0')


def _parse_data_dd_mm(txt: str, vencimento: date | None) -> date | None:
    m = re.match(r'(\d{2})/(\d{2})', txt or '')
    if not m:
        return None
    dia, mes = int(m.group(1)), int(m.group(2))
    if not vencimento:
        return date(date.today().year, mes, dia)
    ano = vencimento.year - 1 if mes > vencimento.month else vencimento.year
    return date(ano, mes, dia)


def _classificar(descricao: str, valor: Decimal) -> str:
    d = _fold(descricao)
    if valor < 0 or 'deb aut' in d or 'pagamento' in d:
        return 'pagamento'
    if d.startswith('iof') or ' iof ' in f' {d} ':
        return 'iof'
    return 'compra'


def _cidade_incompleta(cidade: str) -> bool:
    if not cidade:
        return False
    partes = cidade.split()
    if len(partes) == 1:
        frag = partes[0].upper()
        if frag in {'SAO', 'RIO', 'DE', 'CA', 'SC', 'GUARA', 'BALNEARIO', 'PORTO', 'ITAIM', 'CACHOEIRO'}:
            return True
        if len(frag) <= 4 and frag.isalpha():
            return True
    if partes[-1].upper() in {'DE', 'DO', 'DA', 'RIO', 'SAO'}:
        return True
    return False


def _split_descricao_parcela_cidade(meio: str) -> tuple[str, str, str]:
    meio = ' '.join(meio.split())
    if not meio:
        return '', '', ''

    parcela = ''
    descricao = meio
    cidade = ''

    matches = list(_RE_PARCELA.finditer(meio))
    parcela_match = None
    for m in reversed(matches):
        cand = m.group(1)
        a, b = cand.split('/')
        try:
            if 1 <= int(a) <= 12 and 2 <= int(b) <= 48:
                parcela_match = m
                break
        except ValueError:
            continue

    if parcela_match:
        parcela = parcela_match.group(1)
        descricao = meio[:parcela_match.start()].strip()
        cidade = meio[parcela_match.end():].strip()
    else:
        descricao = meio

    return descricao[:255], parcela, cidade[:80]


def _linha_ignorar(linha: str) -> bool:
    l = _fold(linha)
    if not linha:
        return True
    if linha.startswith('SICOOB') or linha.startswith('SISTEMA DE COOPERATIVAS'):
        return True
    if linha.startswith('PLATAFORMA DE SERVI'):
        return True
    if 'EXTRATO DE CART' in linha.upper()[:40]:
        return True
    if linha.startswith('Cliente:') or linha.startswith('Conta Cart'):
        return True
    if linha.startswith('Fatura de '):
        return True
    if l.startswith('movimentos'):
        return True
    if l.startswith('- saldo anterior'):
        return True
    if l.startswith('total da fatura'):
        return True
    if re.match(r'^total\s+[\d.,]+$', l):
        return False
    if re.match(r'^total\s+', l):
        return True
    if l.startswith('pagamento m'):
        return True
    if l.startswith('limite'):
        return True
    if l.startswith('encargos financeiros'):
        return True
    if l.startswith('rotativo') or l.startswith('saque '):
        return True
    if l.startswith('resumo'):
        return True
    if l.startswith('credito internacional') or l.startswith('debitos'):
        return True
    if l.startswith('saldo '):
        return True
    if l.startswith('perfil de consumo'):
        return True
    if l.startswith('tipo estabelecimento'):
        return True
    if re.match(r'^[a-z].*\d+,\d{2}\s+\d+,\d{2}$', l):
        return True
    if l.startswith('o pagamento total de sua fatura'):
        return True
    if l.startswith('canais de atendimento'):
        return True
    if l.startswith('central de atendimento'):
        return True
    if l.startswith('site:') or l.startswith('ouvidoria'):
        return True
    if l.startswith('deficiente auditivo') or l.startswith('sac:'):
        return True
    if l.startswith('regi') or l.startswith('demais regi') or l.startswith('exterior:'):
        return True
    if l.startswith('24 horas'):
        return True
    return False


def _montar_item(
    data_txt: str,
    meio: str,
    valor_txt: str,
    *,
    vencimento: date | None,
    portador: str,
    final_cartao: str,
    prefixo: str = '',
) -> dict[str, Any] | None:
    data = _parse_data_dd_mm(data_txt, vencimento)
    if not data:
        return None
    valor = _parse_moeda(valor_txt)
    meio_completo = ' '.join(x for x in (prefixo, meio) if x).strip()
    descricao, parcela, cidade = _split_descricao_parcela_cidade(meio_completo)
    if not descricao and not prefixo:
        descricao = meio_completo[:255]
    tipo = _classificar(descricao or meio_completo, valor)
    categoria = ''
    if tipo == 'compra':
        categoria = inferir_categoria(descricao or meio_completo)
    return {
        'data': data,
        'hora': '',
        'cidade': cidade,
        'tipo_compra': '',
        'descricao': descricao or meio_completo[:255],
        'parcela': parcela,
        'categoria': categoria,
        'valor': valor,
        'tipo': tipo,
        'cartao_portador': portador,
        'cartao_final': final_cartao,
    }


def parse_fatura_sicoob_pdf(arquivo) -> dict[str, Any]:
    if pdfplumber is None:
        raise RuntimeError('Biblioteca pdfplumber não instalada.')

    with pdfplumber.open(arquivo) as pdf:
        blob = '\n'.join(page.extract_text() or '' for page in pdf.pages)

    titular = ''
    m_cli = re.search(r'Cliente:\s*(.+)', blob)
    if m_cli:
        titular = m_cli.group(1).strip()

    conta_cartao = ''
    m_conta = re.search(r'Conta Cart[aã]o:\s*(\d+)', blob, re.I)
    if m_conta:
        conta_cartao = m_conta.group(1).strip()

    referencia = ''
    m_ref = re.search(r'Fatura de\s+(\w+)', blob, re.I)
    if m_ref:
        referencia = m_ref.group(1).capitalize()

    vencimento = None
    m_venc = re.search(r'Vencimento:\s*(\d{2}/\d{2}/\d{4})', blob, re.I)
    if m_venc:
        d, m, a = m_venc.group(1).split('/')
        vencimento = date(int(a), int(m), int(d))

    total_fatura = Decimal('0')
    m_tot = re.search(r'Total da Fatura\s+([\d.,]+)', blob, re.I)
    if m_tot:
        total_fatura = _parse_moeda(m_tot.group(1))

    bandeira = 'Mastercard' if 'mastercard' in _fold(blob) else ''
    cartao_final = ''

    itens: list[dict[str, Any]] = []
    cartoes_resumo: list[dict[str, Any]] = []
    portador = ''
    final_cartao = ''
    pendente = ''
    aguardando_continuacao = False

    def _append_item(data_txt: str, meio: str, valor_txt: str, prefixo: str = '') -> None:
        nonlocal aguardando_continuacao
        item = _montar_item(
            data_txt, meio, valor_txt,
            vencimento=vencimento,
            portador=portador,
            final_cartao=final_cartao,
            prefixo=prefixo,
        )
        if item:
            itens.append(item)
            aguardando_continuacao = (
                bool(prefixo)
                or not (item.get('descricao') or '').strip()
                or (bool(prefixo) and _cidade_incompleta(item.get('cidade', '')))
            )

    for linha in blob.splitlines():
        linha = linha.strip()
        if not linha:
            continue

        m_total_secao = re.match(r'^TOTAL\s+([\d.,]+)$', linha, re.I)
        if m_total_secao and final_cartao:
            cartoes_resumo.append({
                'final': final_cartao,
                'portador': portador,
                'total_pdf': float(_parse_moeda(m_total_secao.group(1))),
            })
            continue

        if _linha_ignorar(linha):
            continue

        if linha.startswith('GASTOS DE '):
            portador = linha.replace('GASTOS DE ', '').strip()
            pendente = ''
            aguardando_continuacao = False
            continue

        m_final = _RE_FINAL_CARTAO.match(linha)
        if m_final:
            final_cartao = m_final.group(1)
            if not cartao_final:
                cartao_final = final_cartao
            pendente = ''
            aguardando_continuacao = False
            continue

        if aguardando_continuacao and itens and not _RE_DATA_INICIO.match(linha):
            ultimo = itens[-1]
            if _cidade_incompleta(ultimo.get('cidade', '')):
                ultimo['cidade'] = f"{ultimo['cidade']} {linha}".strip()[:80]
                aguardando_continuacao = _cidade_incompleta(ultimo.get('cidade', ''))
            else:
                ultimo['descricao'] = f"{ultimo['descricao']} {linha}".strip()[:255]
                aguardando_continuacao = True
            continue

        m_dv = _RE_DATA_VALOR.match(linha)
        if m_dv:
            aguardando_continuacao = False
            _append_item(m_dv.group(1), '', m_dv.group(2), prefixo=pendente)
            pendente = ''
            continue

        m_ini = _RE_DATA_INICIO.match(linha)
        if m_ini:
            m_val = _RE_VALOR_FIM.search(linha)
            if m_val:
                aguardando_continuacao = False
                meio = linha[m_ini.end():m_val.start()].strip()
                _append_item(m_ini.group(1), meio, m_val.group(1), prefixo=pendente)
                pendente = ''
                continue
            resto = linha[m_ini.end():].strip()
            pendente = f'{pendente} {resto}'.strip() if pendente else resto
            continue

        if pendente:
            pendente = f'{pendente} {linha}'.strip()
        else:
            pendente = linha

    return {
        'banco': 'Sicoob',
        'titular': titular,
        'conta_cartao': conta_cartao,
        'bandeira': bandeira,
        'cartao_final': cartao_final,
        'cartoes_resumo': cartoes_resumo,
        'referencia_mes': referencia,
        'vencimento': vencimento,
        'total_fatura': total_fatura,
        'itens': itens,
        'qtd_itens': len(itens),
        'perfil_consumo': _parse_perfil_consumo(blob),
    }


def _parse_perfil_consumo(blob: str) -> list[dict[str, Any]]:
    perfil: list[dict[str, Any]] = []
    capturando = False
    for linha in blob.splitlines():
        l = linha.strip()
        if not l:
            continue
        upper = l.upper()
        if 'PERFIL DE CONSUMO' in upper or 'TIPO ESTABELECIMENTO' in upper:
            capturando = True
            continue
        if not capturando:
            continue
        if upper.startswith('O PAGAMENTO TOTAL') or upper.startswith('CANAIS DE ATENDIMENTO'):
            break
        m = re.match(r'^(.+?)\s+([\d.,]+)\s+([\d.,]+)$', l)
        if m:
            perfil.append({
                'tipo': m.group(1).strip(),
                'percentual': float(_parse_moeda(m.group(2))),
                'valor': float(_parse_moeda(m.group(3))),
            })
    return perfil
