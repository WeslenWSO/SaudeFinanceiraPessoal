"""Importação de eventos de cancelamento NFS-e (layout nacional SPED)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dateutil import parser as date_parser

from .models import NotaFiscalServico
from .utils import NS_SPED, _local, safe_print

_RE_SOMENTE_DIGITOS = re.compile(r'\D+')


def _so_digitos(valor: str) -> str:
    return _RE_SOMENTE_DIGITOS.sub('', valor or '')


def _find_text_by_local(root, local_name: str) -> str:
    alvo = local_name.lower()
    for elem in root.iter():
        if _local(elem.tag) == alvo:
            return (elem.text or '').strip()
    return ''


def _parse_data_evento(valor: str) -> date | None:
    if not valor:
        return None
    try:
        dt = date_parser.parse(valor)
        return dt.date() if isinstance(dt, datetime) else dt
    except Exception:
        return None


def is_evento_cancelamento_nfse(root) -> bool:
    if root is None:
        return False
    if _local(root.tag) != 'evento':
        return False
    uri = root.tag[1:].split('}', 1)[0] if root.tag.startswith('{') else ''
    if uri and uri not in ('', NS_SPED):
        return False
    for elem in root.iter():
        loc = _local(elem.tag)
        if loc == 'e101101':
            return True
        if loc == 'chnfse' and _find_text_by_local(root, 'xMotivo'):
            return True
    texto = ET.tostring(root, encoding='unicode', method='text').lower()
    return 'cancelamento de nfs-e' in texto or 'cancelamento de nfse' in texto


def extrair_numero_nota_de_ch_nfse(ch_nfse: str) -> str:
    """
    Extrai nNFSe (13 dígitos) da chave NFS-e nacional.
    Layout: cLocEmi(7) + tpAmb(1) + tpInsc(1) + nInsc(14) + nNFSe(13) + ...
    """
    ch = _so_digitos(ch_nfse)
    if len(ch) < 36:
        return ''
    nnfse = ch[23:36]
    try:
        return str(int(nnfse))
    except ValueError:
        return nnfse.lstrip('0') or ''


def parse_evento_cancelamento(root) -> dict[str, Any]:
    ch_nfse = _find_text_by_local(root, 'chNFSe')
    numero_nota = extrair_numero_nota_de_ch_nfse(ch_nfse)
    dh_evento = _find_text_by_local(root, 'dhEvento') or _find_text_by_local(root, 'dhProc')
    data_cancelamento = _parse_data_evento(dh_evento)
    codigo_motivo = _find_text_by_local(root, 'cMotivo')
    motivo = _find_text_by_local(root, 'xMotivo')
    descricao_evento = _find_text_by_local(root, 'xDesc')
    cnpj_autor = _so_digitos(_find_text_by_local(root, 'CNPJAutor'))

    if not motivo and descricao_evento:
        motivo = descricao_evento

    return {
        'ch_nfse': ch_nfse,
        'numero_nota': numero_nota,
        'data_cancelamento': data_cancelamento,
        'codigo_motivo': codigo_motivo,
        'motivo': motivo,
        'descricao_evento': descricao_evento,
        'cnpj_autor': cnpj_autor,
    }


def zerar_valores_nfse_cancelada(nfse: NotaFiscalServico) -> None:
    zero = Decimal('0')
    nfse.valor_bruto = zero
    nfse.valor_liquido = zero
    nfse.valor_deducoes = zero
    nfse.valor_pis = zero
    nfse.valor_cofins = zero
    nfse.valor_inss = zero
    nfse.valor_ir = zero
    nfse.valor_csll = zero
    nfse.valor_iss_retido = zero
    nfse.outras_retencoes = zero
    nfse.aliquota = zero
    nfse.issapuracao = zero
    nfse.pisapuracao = zero
    nfse.cofinsapuracao = zero
    nfse.csllapuracao = zero
    nfse.irpjapuracao = zero
    nfse.irpjadicional = zero
    if hasattr(nfse, 'valor_recebido'):
        nfse.valor_recebido = zero


def _periodo_fechado(empresa, data_ref: date) -> bool:
    from .models import ApuracaoPeriodo
    if not data_ref:
        return False
    return ApuracaoPeriodo.objects.filter(
        empresa=empresa,
        data_inicio__lte=data_ref,
        data_fim__gte=data_ref,
        status='fechado',
    ).exists()


def localizar_nota_por_evento(empresa, numero_nota: str, ch_nfse: str = '') -> NotaFiscalServico | None:
    if not numero_nota:
        return None
    qs = NotaFiscalServico.objects.filter(
        empresa=empresa,
        numero_nota=str(numero_nota),
    )
    if ch_nfse:
        por_chave = qs.filter(nsu=ch_nfse).first()
        if por_chave:
            return por_chave
    if qs.count() == 1:
        return qs.first()
    return qs.order_by('-data_emissao', '-id').first()


def aplicar_cancelamento_por_evento(
    nfse: NotaFiscalServico,
    *,
    data_cancelamento: date | None,
    codigo_motivo: str,
    motivo: str,
) -> None:
    if not nfse.data_cancelamento and data_cancelamento:
        nfse.data_cancelamento = data_cancelamento
    elif not nfse.data_cancelamento:
        nfse.data_cancelamento = date.today()
    nfse.codigo_motivo_cancelamento = (codigo_motivo or '')[:10]
    nfse.motivo_cancelamento = (motivo or '').strip()
    zerar_valores_nfse_cancelada(nfse)


def import_evento_cancelamento_nfse(xml_file, user, empresa) -> dict[str, Any]:
    """Processa XML de evento de cancelamento e atualiza a NFSe no sistema."""
    resultado = {
        'tipo': 'evento_cancelamento',
        'notas_importadas': [],
        'notas_canceladas': [],
        'notas_ignoradas': [],
        'total_processadas': 0,
        'total_importadas': 0,
        'total_canceladas': 0,
        'total_ignoradas': 0,
    }

    try:
        if hasattr(xml_file, 'seek'):
            xml_file.seek(0)
        tree = ET.parse(xml_file.file if hasattr(xml_file, 'file') else xml_file)
        root = tree.getroot()
    except Exception as exc:
        raise ValueError(f'Erro ao ler XML de evento: {exc}') from exc

    if not is_evento_cancelamento_nfse(root):
        raise ValueError('XML não é um evento de cancelamento NFS-e.')

    dados = parse_evento_cancelamento(root)
    resultado['total_processadas'] = 1
    safe_print(f"=== Evento cancelamento NFSe: nota {dados.get('numero_nota')} ch={dados.get('ch_nfse')}")

    cnpj_empresa = _so_digitos(getattr(empresa, 'cnpj', ''))
    if dados.get('cnpj_autor') and cnpj_empresa and dados['cnpj_autor'] != cnpj_empresa:
        resultado['notas_ignoradas'].append({
            'numero_nota': dados.get('numero_nota') or '?',
            'cliente': '',
            'motivo': (
                f"CNPJ do evento ({dados['cnpj_autor']}) difere da empresa selecionada ({cnpj_empresa})."
            ),
        })
        resultado['total_ignoradas'] = 1
        return resultado

    if not dados.get('numero_nota'):
        resultado['notas_ignoradas'].append({
            'numero_nota': '?',
            'cliente': '',
            'motivo': 'Não foi possível identificar o número da NFSe no evento (chNFSe inválida).',
        })
        resultado['total_ignoradas'] = 1
        return resultado

    nfse = localizar_nota_por_evento(empresa, dados['numero_nota'], dados.get('ch_nfse', ''))
    if not nfse:
        resultado['notas_ignoradas'].append({
            'numero_nota': dados['numero_nota'],
            'cliente': '',
            'motivo': f"NFSe {dados['numero_nota']} não encontrada no sistema.",
        })
        resultado['total_ignoradas'] = 1
        return resultado

    data_ref = dados.get('data_cancelamento') or nfse.data_emissao
    if _periodo_fechado(empresa, data_ref):
        resultado['notas_ignoradas'].append({
            'numero_nota': nfse.numero_nota,
            'cliente': nfse.cliente,
            'motivo': 'Período fechado — reabra o período em Apuração de Impostos para cancelar a nota.',
        })
        resultado['total_ignoradas'] = 1
        return resultado

    if nfse.is_cancelada():
        nfse.codigo_motivo_cancelamento = (dados.get('codigo_motivo') or '')[:10]
        nfse.motivo_cancelamento = (dados.get('motivo') or '').strip()
        nfse.save(update_fields=[
            'codigo_motivo_cancelamento',
            'motivo_cancelamento',
            'data_atualizacao',
        ])
        resultado['notas_ignoradas'].append({
            'numero_nota': nfse.numero_nota,
            'cliente': nfse.cliente,
            'motivo': 'NFSe já estava cancelada (motivo atualizado).',
        })
        resultado['total_ignoradas'] = 1
        return resultado

    aplicar_cancelamento_por_evento(
        nfse,
        data_cancelamento=dados.get('data_cancelamento'),
        codigo_motivo=dados.get('codigo_motivo', ''),
        motivo=dados.get('motivo', ''),
    )
    nfse.save()

    item = {
        'numero_nota': nfse.numero_nota,
        'cliente': nfse.cliente,
        'motivo': dados.get('motivo') or 'Cancelamento via evento NFS-e',
        'data_cancelamento': nfse.data_cancelamento.isoformat() if nfse.data_cancelamento else '',
    }
    resultado['notas_canceladas'].append(item)
    resultado['notas_importadas'].append(item)
    resultado['total_canceladas'] = 1
    resultado['total_importadas'] = 1
    return resultado


def extract_evento_cancelamento_preview(root, empresa) -> list[dict]:
    if not is_evento_cancelamento_nfse(root):
        return []
    dados = parse_evento_cancelamento(root)
    numero = dados.get('numero_nota') or '?'
    nfse = None
    if dados.get('numero_nota'):
        nfse = localizar_nota_por_evento(empresa, dados['numero_nota'], dados.get('ch_nfse', ''))

    if nfse:
        if nfse.is_cancelada():
            status = 'ja_cancelada'
            msg = 'NFSe já cancelada no sistema'
        else:
            status = 'valido'
            msg = 'Será marcada como cancelada (valores zerados)'
    else:
        status = 'invalido'
        msg = f"NFSe {numero} não encontrada no sistema"

    return [{
        'numero_nota': numero,
        'serie': nfse.serie if nfse else '',
        'data_emissao': dados.get('data_cancelamento').strftime('%Y-%m-%d') if dados.get('data_cancelamento') else '',
        'valor_bruto': '0.00',
        'valor_liquido': '0.00',
        'cliente': nfse.cliente if nfse else '—',
        'cnpj_cpf': nfse.cnpj_cpf if nfse else '',
        'discriminacao': f"Evento: {dados.get('descricao_evento') or 'Cancelamento'} — {dados.get('motivo') or ''}",
        'status': status,
        'mensagem': msg,
        'tipo': 'evento_cancelamento',
    }]
