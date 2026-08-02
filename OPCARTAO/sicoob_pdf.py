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
_RE_GASTOS = re.compile(r'^GASTOS DE\s+(.+?)(?:\s+\((\d{4})\))\s*$', re.I)
_RE_GASTOS_SEM_FINAL = re.compile(r'^GASTOS DE\s+(.+)$', re.I)
_RE_TIMESTAMP = re.compile(r'^\d{2}/\d{2}/\d{4}')


def _fold(s: str) -> str:
    if not s:
        return ''
    d = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in d if unicodedata.category(c) != 'Mn').lower()


def _clip(s: str, n: int) -> str:
    return (s or '')[:n]


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
    try:
        if not vencimento:
            return date(date.today().year, mes, dia)
        ano = vencimento.year - 1 if mes > vencimento.month else vencimento.year
        return date(ano, mes, dia)
    except ValueError:
        return None


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

    return _clip(descricao, 255), parcela, _clip(cidade, 80)


def _linha_ignorar(linha: str) -> bool:
    l = _fold(linha)
    if not linha:
        return True
    if _RE_TIMESTAMP.match(linha):
        return True
    if 'internet banking' in l or 'sicoob |' in l:
        return True
    if linha.startswith('SICOOB') or linha.startswith('SISTEMA DE COOPERATIVAS'):
        return True
    if 'sisbr' in l:
        return True
    if linha.startswith('PLATAFORMA DE SERVI'):
        return True
    if 'extrato de fatura' in l or 'extrato de cart' in l:
        return True
    if linha.startswith('Cliente:') or linha.startswith('Conta Cart'):
        return True
    if l.startswith('fatura de '):
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
    # Remove lixo de câmbio embutido na descrição (U$ / V.DOL)
    meio_limpo = re.sub(
        r'\s*R\$\s*[\d.,]+\s+U\$\s*[\d.,]+\s+V\.?DOL\s*[\d.,]+',
        '',
        meio_completo,
        flags=re.I,
    ).strip() or meio_completo
    descricao, parcela, cidade = _split_descricao_parcela_cidade(meio_limpo)
    if not descricao and not prefixo:
        descricao = _clip(meio_limpo, 255)
    tipo = _classificar(descricao or meio_limpo, valor)
    categoria = ''
    if tipo == 'compra':
        categoria = _clip(inferir_categoria(descricao or meio_limpo), 30)
    return {
        'data': data,
        'hora': '',
        'cidade': cidade,
        'tipo_compra': '',
        'descricao': descricao or _clip(meio_limpo, 255),
        'parcela': _clip(parcela, 10),
        'categoria': categoria,
        'valor': valor,
        'tipo': tipo,
        'cartao_portador': _clip(portador, 120),
        'cartao_final': _clip(final_cartao, 8),
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
    if not titular:
        m_tit = re.search(
            r'EXTRATO DE FATURA[^\n]*\n([A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ][^\n]{2,80})\nConta Cart',
            blob,
            re.I,
        )
        if m_tit:
            titular = m_tit.group(1).strip()

    conta_cartao = ''
    m_conta = re.search(r'Conta Cart[aã]o:\s*(\d+)', blob, re.I)
    if m_conta:
        conta_cartao = m_conta.group(1).strip()

    referencia = ''
    m_ref = re.search(
        r'Fatura de\s+([A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+)\s+Vencimento',
        blob,
        re.I,
    )
    if m_ref:
        referencia = m_ref.group(1).strip().capitalize()

    vencimento = None
    m_venc = re.search(r'Vencimento:\s*(\d{2}/\d{2}/\d{4})', blob, re.I)
    if m_venc:
        d, m, a = m_venc.group(1).split('/')
        vencimento = date(int(a), int(m), int(d))

    total_fatura = Decimal('0')
    m_tot = re.search(r'Total da Fatura\s+([\d.,]+)', blob, re.I)
    if m_tot:
        total_fatura = _parse_moeda(m_tot.group(1))

    bandeira = ''
    blob_fold = _fold(blob)
    if 'visa' in blob_fold:
        bandeira = 'Visa'
    elif 'mastercard' in blob_fold or 'master card' in blob_fold:
        bandeira = 'Mastercard'

    cartao_final = ''
    itens: list[dict[str, Any]] = []
    cartoes_resumo: list[dict[str, Any]] = []
    portador = ''
    final_cartao = ''
    pendente_data = ''
    pendente_meio = ''
    aguardando_continuacao = False

    def _flush_pendente_com_valor(valor_txt: str) -> None:
        nonlocal pendente_data, pendente_meio, aguardando_continuacao
        if not pendente_data:
            return
        item = _montar_item(
            pendente_data, pendente_meio, valor_txt,
            vencimento=vencimento,
            portador=portador,
            final_cartao=final_cartao,
        )
        if item:
            itens.append(item)
            aguardando_continuacao = _cidade_incompleta(item.get('cidade', ''))
        pendente_data = ''
        pendente_meio = ''

    def _append_item(data_txt: str, meio: str, valor_txt: str) -> None:
        nonlocal aguardando_continuacao, pendente_data, pendente_meio
        # Se havia descrição pendente de outra data, descarta (evita misturar compras)
        pendente_data = ''
        pendente_meio = ''
        item = _montar_item(
            data_txt, meio, valor_txt,
            vencimento=vencimento,
            portador=portador,
            final_cartao=final_cartao,
        )
        if item:
            itens.append(item)
            aguardando_continuacao = (
                not (item.get('descricao') or '').strip()
                or _cidade_incompleta(item.get('cidade', ''))
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

        m_gastos = _RE_GASTOS.match(linha) or _RE_GASTOS_SEM_FINAL.match(linha)
        if m_gastos:
            portador = m_gastos.group(1).strip()
            if m_gastos.lastindex and m_gastos.lastindex >= 2 and m_gastos.group(2):
                final_cartao = m_gastos.group(2)
                if not cartao_final:
                    cartao_final = final_cartao
            pendente_data = ''
            pendente_meio = ''
            aguardando_continuacao = False
            continue

        if _linha_ignorar(linha):
            continue

        m_final = _RE_FINAL_CARTAO.match(linha)
        if m_final:
            final_cartao = m_final.group(1)
            if not cartao_final:
                cartao_final = final_cartao
            pendente_data = ''
            pendente_meio = ''
            aguardando_continuacao = False
            continue

        # Continuação de compra internacional (R$ ... U$ ... valor)
        if pendente_data and not _RE_DATA_INICIO.match(linha):
            m_val = _RE_VALOR_FIM.search(linha)
            if m_val:
                extra = linha[:m_val.start()].strip()
                if extra:
                    pendente_meio = f'{pendente_meio} {extra}'.strip()
                _flush_pendente_com_valor(m_val.group(1))
                continue

        if aguardando_continuacao and itens and not _RE_DATA_INICIO.match(linha):
            ultimo = itens[-1]
            if _cidade_incompleta(ultimo.get('cidade', '')):
                ultimo['cidade'] = _clip(f"{ultimo['cidade']} {linha}".strip(), 80)
                aguardando_continuacao = _cidade_incompleta(ultimo.get('cidade', ''))
            else:
                ultimo['descricao'] = _clip(f"{ultimo['descricao']} {linha}".strip(), 255)
                aguardando_continuacao = False
            continue

        m_dv = _RE_DATA_VALOR.match(linha)
        if m_dv:
            aguardando_continuacao = False
            _append_item(m_dv.group(1), '', m_dv.group(2))
            continue

        m_ini = _RE_DATA_INICIO.match(linha)
        if m_ini:
            m_val = _RE_VALOR_FIM.search(linha)
            if m_val:
                aguardando_continuacao = False
                meio = linha[m_ini.end():m_val.start()].strip()
                _append_item(m_ini.group(1), meio, m_val.group(1))
                continue
            # Linha de data sem valor: guarda para juntar com a próxima (ex.: OPENAI)
            pendente_data = m_ini.group(1)
            pendente_meio = linha[m_ini.end():].strip()
            aguardando_continuacao = False
            continue

        # Sem data: só acumula se já há compra incompleta
        if pendente_data:
            pendente_meio = f'{pendente_meio} {linha}'.strip()
            m_val = _RE_VALOR_FIM.search(pendente_meio)
            if m_val:
                pendente_meio = pendente_meio[:m_val.start()].strip()
                _flush_pendente_com_valor(m_val.group(1))
            continue

    return {
        'banco': 'Sicoob',
        'titular': _clip(titular, 120),
        'conta_cartao': _clip(conta_cartao, 30),
        'bandeira': _clip(bandeira, 30),
        'cartao_final': _clip(cartao_final, 8),
        'cartoes_resumo': cartoes_resumo,
        'referencia_mes': _clip(referencia, 30),
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
                'tipo': m.group(1).strip()[:80],
                'percentual': float(_parse_moeda(m.group(2))),
                'valor': float(_parse_moeda(m.group(3))),
            })
    return perfil
