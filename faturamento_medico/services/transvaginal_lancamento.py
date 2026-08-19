"""Lançamento separado para exames transvaginais (sem guia e senha)."""

from __future__ import annotations

from copy import copy

from django.db import transaction

from faturamento_medico.models import FaturamentoMedico, ItemServico
from faturamento_medico.procedimento_utils import eh_procedimento_transvaginal

_CAMPOS_CLONAR = (
    'carteirinha',
    'cpf',
    'nome',
    'nome_associado',
    'data',
    'local',
    'medico',
    'anestesista',
    'medico_solicitante',
    'tecnico',
    'checkin_por',
    'agendado_por',
    'convenio',
    'receber_por',
    'apartamento_enfermaria',
    'urgencia',
    'observacao',
    'horario',
    'horario_inicio',
    'horario_fim',
    'prioridade',
    'status_agendamento',
    'motivo_cancelamento',
    'tag',
    'indicacao_clinica',
    'descricao',
    'agendado_via',
    'codigo_relatorio',
)


def linha_planilha_sem_guia(linha):
    """Remove guia/senha da linha de planilha (transvaginal não usa autorização)."""
    nova = copy(linha)
    nova.guia = ''
    nova.senha = ''
    nova.numero_guia_lancada = ''
    return nova


def _criar_faturamento_transvaginal(origem: FaturamentoMedico) -> FaturamentoMedico:
    dados = {campo: getattr(origem, campo) for campo in _CAMPOS_CLONAR}
    return FaturamentoMedico.objects.create(
        empresa_id=origem.empresa_id,
        status='pendente',
        guia='',
        senha='',
        guia_lancada='',
        numero_guia_lancada='',
        lote='',
        **dados,
    )


def _faturamento_so_transvaginal(fat: FaturamentoMedico) -> bool:
    itens = list(fat.itens_servico.all())
    return bool(itens) and all(eh_procedimento_transvaginal(i.servico) for i in itens)


def obter_faturamento_transvaginal(origem: FaturamentoMedico) -> FaturamentoMedico:
    """Faturamento dedicado ao transvaginal (sem guia/senha) do mesmo paciente/data/convênio."""
    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=origem.empresa_id,
            data=origem.data,
            nome=origem.nome,
            convenio=origem.convenio,
        )
        .filter(guia__in=('', None))
        .filter(senha__in=('', None))
        .exclude(pk=origem.pk)
        .prefetch_related('itens_servico')
    )
    for candidato in qs.order_by('pk'):
        if _faturamento_so_transvaginal(candidato):
            return candidato
    return _criar_faturamento_transvaginal(origem)


@transaction.atomic
def separar_item_transvaginal(item: ItemServico) -> ItemServico:
    """
    Move item transvaginal para faturamento próprio, sem número de guia e senha.
    Idempotente se já estiver correto.
    """
    if not eh_procedimento_transvaginal(item.servico):
        return item

    fat = item.faturamento
    sem_guia = not (fat.guia or '').strip() and not (fat.senha or '').strip()
    unico = fat.itens_servico.count() == 1

    if unico and sem_guia:
        return item

    destino = obter_faturamento_transvaginal(fat)
    if item.faturamento_id == destino.pk:
        return item

    item.faturamento = destino
    item.save(update_fields=['faturamento'])
    fat.atualizar_total()
    destino.atualizar_total()
    return item


def separar_todos_transvaginais(*, empresa_id: int | None = None, dry_run: bool = False) -> dict:
    """Corrige lançamentos existentes no banco (produção)."""
    from django.db.models import Count

    qs = (
        ItemServico.objects.select_related('faturamento')
        .filter(servico__iregex=r'transvag')
        .annotate(qtd_itens_fat=Count('faturamento__itens_servico'))
    )
    if empresa_id:
        qs = qs.filter(faturamento__empresa_id=empresa_id)

    stats = {'analisados': 0, 'separados': 0, 'detalhes': []}
    for item in qs.iterator():
        stats['analisados'] += 1
        fat = item.faturamento
        precisa = (
            (fat.guia or '').strip()
            or (fat.senha or '').strip()
            or item.qtd_itens_fat > 1
        )
        if not precisa:
            continue
        if dry_run:
            stats['separados'] += 1
            stats['detalhes'].append(
                f'DRY item #{item.id} fat #{fat.id} -> novo lançamento sem guia/senha'
            )
            continue
        antes = item.faturamento_id
        separar_item_transvaginal(item)
        item.refresh_from_db()
        if item.faturamento_id != antes:
            stats['separados'] += 1
            stats['detalhes'].append(
                f'item #{item.id}: fat #{antes} -> fat #{item.faturamento_id} (sem guia/senha)'
            )
    return stats
