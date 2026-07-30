"""Tarefas a vencer para o letreiro (2 dias antes do prazo)."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from agendador_tarefas.models import TarefaAgendada


def aliases_responsavel(user) -> list[str]:
    nomes: list[str] = []
    if user and user.is_authenticated:
        completo = (user.get_full_name() or '').strip()
        if completo:
            nomes.append(completo)
        username = (user.username or '').strip()
        if username and username not in nomes:
            nomes.append(username)
    return nomes


def _filtro_responsavel(user):
    aliases = aliases_responsavel(user)
    if not aliases:
        return None
    filtro = Q(responsavel='')
    for nome in aliases:
        filtro |= Q(responsavel__iexact=nome)
    return filtro


def tarefas_vencendo_queryset(user, *, empresa_id=None):
    """Pendentes com previsão até 2 dias à frente (inclui vencidas)."""
    filtro_resp = _filtro_responsavel(user)
    if filtro_resp is None:
        return TarefaAgendada.objects.none()

    hoje = timezone.localdate()
    limite = hoje + timedelta(days=2)

    from empresa.models import UsuarioEmpresa

    filtro_empresa = Q(empresa__isnull=True)
    if empresa_id:
        filtro_empresa |= Q(empresa_id=empresa_id)
    else:
        empresa_ids = list(
            UsuarioEmpresa.objects.filter(
                usuario=user,
                ativo=True,
                empresa__status='Ativa',
            ).values_list('empresa_id', flat=True)
        )
        if empresa_ids:
            filtro_empresa |= Q(empresa_id__in=empresa_ids)

    return (
        TarefaAgendada.objects.filter(filtro_empresa)
        .filter(
            status__in=(
                TarefaAgendada.STATUS_PENDENTE,
                TarefaAgendada.STATUS_COM_SUPERVISOR,
            ),
            previsao_conclusao__lte=limite,
        )
        .filter(filtro_resp)
        .select_related('empresa')
        .order_by('previsao_conclusao', 'hora_inicio', 'titulo')
    )


def _rotulo_prazo(hoje, previsao) -> str:
    if previsao < hoje:
        dias = (hoje - previsao).days
        if dias == 1:
            return 'VENCIDA ontem'
        return f'VENCIDA há {dias} dias'
    if previsao == hoje:
        return 'vence HOJE'
    if previsao == hoje + timedelta(days=1):
        return 'vence amanhã'
    return f'vence em {previsao.strftime("%d/%m/%Y")}'


def mensagens_letreiro_usuario(user, *, empresa_id=None) -> list[dict]:
    """Textos do letreiro: responsável × empresa × tarefa."""
    hoje = timezone.localdate()
    mensagens: list[dict] = []
    responsavel_padrao = (aliases_responsavel(user) or [''])[0]

    for tarefa in tarefas_vencendo_queryset(user, empresa_id=empresa_id):
        emp = tarefa.empresa_rotulo
        prazo = _rotulo_prazo(hoje, tarefa.previsao_conclusao)
        resp = (tarefa.responsavel or '').strip() or responsavel_padrao or 'Sem responsável'
        hora = f' {tarefa.horario_rotulo}' if tarefa.horario_rotulo else ''
        texto = (
            f'{resp} · {emp} · {tarefa.titulo}{hora} — {prazo} '
            f'(comp. {tarefa.competencia_rotulo})'
        )
        mensagens.append({
            'texto': texto,
            'url': reverse('agendador_tarefas:editar', args=[tarefa.pk]),
        })
    return mensagens
