"""Gera/vincula lotes internos agrupados por lote + protocolo do convênio (ex.: GEAP)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from faturamento_medico.lote_utils import (
    faturamento_elegivel_lote,
    faturamento_tem_lote_interno,
    ids_lotes_internos,
)
from faturamento_medico.models import FaturamentoMedico, ItemServico, Lote


def _valor_conferido_faturamento(fat: FaturamentoMedico) -> Decimal:
    total = (
        ItemServico.objects.filter(faturamento=fat)
        .filter(Q(conferido=True) | Q(status_conferencia='CONFERIDO'))
        .aggregate(s=Sum('total'))['s']
    )
    if total is not None:
        return Decimal(str(total))
    total = (
        ItemServico.objects.filter(faturamento=fat)
        .filter(Q(conferido=True) | Q(status_conferencia='CONFERIDO'))
        .aggregate(s=Sum('valor'))['s']
    )
    return Decimal(str(total or 0))


def _agrupar_por_lote_protocolo(
    faturamentos: list[FaturamentoMedico],
    *,
    ids_internos: set[str],
) -> tuple[dict[tuple[str, str], list[FaturamentoMedico]], list[str]]:
    grupos: dict[tuple[str, str], list[FaturamentoMedico]] = defaultdict(list)
    erros: list[str] = []

    for fat in faturamentos:
        if faturamento_tem_lote_interno(fat, ids_internos=ids_internos):
            erros.append(f'#{fat.id} já possui lote interno.')
            continue
        if not faturamento_elegivel_lote(fat, ids_internos=ids_internos):
            erros.append(f'#{fat.id} pendente de conferência ou indisponível.')
            continue
        lote_conv = (fat.lote or '').strip()
        protocolo = (fat.guia_lancada or '').strip()
        if not lote_conv or not protocolo:
            erros.append(
                f'#{fat.id} sem lote ou protocolo (guia lançada) preenchidos no faturamento.'
            )
            continue
        if lote_conv in ids_internos:
            erros.append(f'#{fat.id} lote inválido ou já vinculado.')
            continue
        grupos[(lote_conv, protocolo)].append(fat)

    return grupos, erros


def _criar_lotes_dos_grupos(
    grupos: dict[tuple[str, str], list[FaturamentoMedico]],
    *,
    empresa_id: int,
    dry_run: bool = False,
) -> dict:
    stats = {
        'grupos': len(grupos),
        'faturamentos': sum(len(v) for v in grupos.values()),
        'lotes_criados': [],
        'detalhes': [],
    }

    for (lote_conv, protocolo), fats in sorted(grupos.items(), key=lambda x: (x[0][0], x[0][1])):
        valor = sum(_valor_conferido_faturamento(f) for f in fats)
        convenio_nome = (fats[0].convenio or '').strip()
        if dry_run:
            stats['lotes_criados'].append(f'DRY lote_conv={lote_conv} prot={protocolo}')
            stats['detalhes'].append(
                f'DRY-RUN lote conv. {lote_conv} | protocolo {protocolo} | '
                f'{len(fats)} guia(s) | R$ {valor:.2f}'
            )
            continue

        lote = Lote.objects.create(empresa_id=empresa_id, convenio=convenio_nome)
        fat_ids = [f.id for f in fats]
        FaturamentoMedico.objects.filter(id__in=fat_ids).update(
            lote=str(lote.id),
            status='aguardando_pagamento',
        )
        lote.total_lote = valor
        lote.save(update_fields=['total_lote'])
        lote.sincronizar_extrato_pagamento(lote_convenio=lote_conv, protocolo=protocolo)
        stats['lotes_criados'].append(lote.id)
        stats['detalhes'].append(
            f'Lote interno #{lote.id} | lote conv. {lote_conv} | protocolo {protocolo} | '
            f'{len(fats)} guia(s) | R$ {lote.total_lote:.2f}'
        )

    return stats


def vincular_lote_protocolo_selecionados(
    *,
    empresa_id: int,
    faturamento_ids: list[int],
    dry_run: bool = False,
) -> dict:
    """Vincula guias selecionadas aos lotes/protocolos já informados no faturamento."""
    ids_internos = ids_lotes_internos(empresa_id)
    faturamentos = list(
        FaturamentoMedico.objects.filter(
            id__in=faturamento_ids,
            empresa_id=empresa_id,
        ).prefetch_related('itens_servico')
    )
    if not faturamentos:
        return {
            'grupos': 0,
            'faturamentos': 0,
            'ignorados': len(faturamento_ids),
            'lotes_criados': [],
            'detalhes': [],
            'erros': ['Nenhum faturamento encontrado.'],
        }

    grupos, erros = _agrupar_por_lote_protocolo(faturamentos, ids_internos=ids_internos)
    stats = _criar_lotes_dos_grupos(grupos, empresa_id=empresa_id, dry_run=dry_run)
    stats['ignorados'] = len(faturamentos) - stats['faturamentos']
    stats['erros'] = erros[:20]
    if len(erros) > 20:
        stats['erros'].append(f'… +{len(erros) - 20} aviso(s)')
    return stats


def gerar_lotes_por_lote_protocolo(
    *,
    empresa_id: int,
    convenio: str = 'GEAP',
    data_inicio: date | None = None,
    data_fim: date | None = None,
    dry_run: bool = False,
) -> dict:
    ids_internos = ids_lotes_internos(empresa_id)
    qs = FaturamentoMedico.objects.filter(
        empresa_id=empresa_id,
        convenio__icontains=convenio,
        status='pendente',
    ).prefetch_related('itens_servico')

    if data_inicio:
        qs = qs.filter(data__gte=data_inicio)
    if data_fim:
        qs = qs.filter(data__lte=data_fim)

    faturamentos = [f for f in qs if not faturamento_tem_lote_interno(f, ids_internos=ids_internos)]
    grupos, erros = _agrupar_por_lote_protocolo(faturamentos, ids_internos=ids_internos)
    stats = _criar_lotes_dos_grupos(grupos, empresa_id=empresa_id, dry_run=dry_run)
    stats['ignorados'] = len(faturamentos) - stats['faturamentos'] + (
        qs.count() - len(faturamentos)
    )
    stats['erros'] = erros[:20]
    return stats
