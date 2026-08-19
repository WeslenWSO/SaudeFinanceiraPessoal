"""Utilitários para distinguir lote interno (modelo Lote) do lote do convênio (GEAP etc.)."""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from .models import ExtratoPagamentoConvenio, FaturamentoMedico, Lote


def ids_lotes_internos(empresa_id: int) -> set[str]:
    return {str(pk) for pk in Lote.objects.filter(empresa_id=empresa_id).values_list('id', flat=True)}


def chave_agrupamento_lote_impressao(
    convenio: str | None,
    protocolo: str | None,
    lote_convenio: str | None,
) -> tuple[str, str, str]:
    """Chave única para agrupar lotes internos com mesmo protocolo + lote do convênio."""
    return (
        (convenio or '').strip().upper(),
        (protocolo or '').strip(),
        (lote_convenio or '').strip(),
    )


def _convenios_compativeis(a: str, b: str) -> bool:
    au = (a or '').strip().upper()
    bu = (b or '').strip().upper()
    if not au or not bu:
        return True
    return au == bu or au in bu or bu in au


def buscar_lote_interno_aberto_por_extrato(
    *,
    empresa_id: int,
    convenio: str,
    lote_convenio: str,
    protocolo: str = '',
) -> Lote | None:
    """Lote interno não baixado já vinculado ao mesmo lote/protocolo do convênio."""
    lote_conv = (lote_convenio or '').strip()
    if not lote_conv:
        return None
    prot = (protocolo or '').strip()
    qs = ExtratoPagamentoConvenio.objects.filter(
        empresa_id=empresa_id,
        lote=lote_conv,
        lote_faturamento__baixado=False,
        lote_faturamento__isnull=False,
    ).select_related('lote_faturamento')
    if prot:
        qs = qs.filter(protocolo=prot)
    else:
        qs = qs.filter(protocolo='')
    for extrato in qs.order_by('-lote_faturamento_id'):
        lote = extrato.lote_faturamento
        if lote and _convenios_compativeis(convenio, extrato.convenio or lote.convenio or ''):
            return lote
    return None


def agrupar_lotes_para_impressao(lotes) -> list[dict]:
    """
    Agrupa lotes internos com o mesmo convênio + protocolo + lote convênio
    para exibir uma única opção na impressão.
    """
    grupos: OrderedDict[tuple[str, str, str], dict] = OrderedDict()
    for lote in lotes:
        extrato = lote.linhas_extrato_pagamento.first()
        protocolo = (extrato.protocolo if extrato else '').strip()
        lote_conv = (extrato.lote if extrato else '').strip()
        if not lote_conv:
            lote_conv = str(lote.id)
        chave = chave_agrupamento_lote_impressao(lote.convenio, protocolo, lote_conv)
        if chave not in grupos:
            grupos[chave] = {
                'lote_ids': [lote.id],
                'lote_id_label': lote.id,
                'convenio': lote.convenio or '',
                'protocolo': protocolo,
                'lote_convenio': lote_conv,
                'total': Decimal(str(lote.total_lote or 0)),
            }
        else:
            grupo = grupos[chave]
            if lote.id not in grupo['lote_ids']:
                grupo['lote_ids'].append(lote.id)
            grupo['lote_id_label'] = max(grupo['lote_ids'])
            grupo['total'] += Decimal(str(lote.total_lote or 0))
    resultado = []
    for grupo in grupos.values():
        grupo['lote_ids'].sort()
        grupo['lote_ids_csv'] = ','.join(str(i) for i in grupo['lote_ids'])
        grupo['qtd_lotes'] = len(grupo['lote_ids'])
        resultado.append(grupo)
    resultado.sort(key=lambda g: g['lote_id_label'], reverse=True)
    return resultado


def parse_lote_ids(valor) -> list[int]:
    """Converte '48' ou '47,48' em lista de IDs de lote interno."""
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        bruto = valor
    else:
        bruto = str(valor).replace(';', ',').split(',')
    ids: list[int] = []
    for parte in bruto:
        parte = str(parte).strip()
        if not parte:
            continue
        try:
            lid = int(parte)
        except (TypeError, ValueError):
            continue
        if lid not in ids:
            ids.append(lid)
    return ids


def ids_lotes_internos(empresa_id: int) -> set[str]:
    return {str(pk) for pk in Lote.objects.filter(empresa_id=empresa_id).values_list('id', flat=True)}


def faturamento_tem_lote_interno(
    faturamento: FaturamentoMedico,
    *,
    ids_internos: set[str] | None = None,
) -> bool:
    lote = (faturamento.lote or '').strip()
    if not lote:
        return False
    if ids_internos is None:
        ids_internos = ids_lotes_internos(faturamento.empresa_id)
    return lote in ids_internos


def faturamento_elegivel_lote(faturamento: FaturamentoMedico, *, ids_internos: set[str] | None = None) -> bool:
    """Pendente, sem lote interno, com itens conferidos."""
    if (faturamento.status or '').strip() != 'pendente':
        return False
    if faturamento_tem_lote_interno(faturamento, ids_internos=ids_internos):
        return False
    return faturamento.itens_servico.filter(conferido=True).exists()


def marcar_itens_faturamento_lote_ok(faturamento: FaturamentoMedico) -> int:
    """Marca itens conferidos como LOTE OK após vincular lote interno."""
    from django.db.models import Q

    from .models import ItemServico

    atualizados = 0
    qs = ItemServico.objects.filter(faturamento=faturamento).filter(
        Q(conferido=True)
        | Q(status_conferencia__in=('CONFERIDO', 'LOTE OK'))
    )
    for item in qs:
        if item.status_conferencia == 'LOTE OK' and item.conferido:
            continue
        item.status_conferencia = 'LOTE OK'
        item.conferido = True
        item.save(update_fields=['status_conferencia', 'conferido'])
        atualizados += 1
    return atualizados
