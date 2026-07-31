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


def usuario_ve_todas_tarefas(user) -> bool:
    """Usuário saude (e superusuários) enxergam todas as tarefas no letreiro."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (user.username or '').strip().lower() == 'saude'


def _empresa_ids_usuario(user) -> list[int]:
    from empresa.models import UsuarioEmpresa

    return list(
        UsuarioEmpresa.objects.filter(
            usuario=user,
            ativo=True,
            empresa__status='Ativa',
        ).values_list('empresa_id', flat=True)
    )


def _filtro_responsavel(user):
    aliases = aliases_responsavel(user)
    if not aliases:
        return None
    filtro = None
    for nome in aliases:
        cond = Q(responsavel__iexact=nome)
        filtro = cond if filtro is None else filtro | cond
    return filtro


def tarefas_vencendo_queryset(user):
    """Pendentes com previsão até 2 dias à frente (inclui vencidas)."""
    if not user or not user.is_authenticated:
        return TarefaAgendada.objects.none()

    hoje = timezone.localdate()
    limite = hoje + timedelta(days=2)

    base = (
        TarefaAgendada.objects.filter(
            status__in=(
                TarefaAgendada.STATUS_PENDENTE,
                TarefaAgendada.STATUS_COM_SUPERVISOR,
            ),
            previsao_conclusao__lte=limite,
        )
        .select_related('empresa')
        .order_by('previsao_conclusao', 'hora_inicio', 'titulo')
    )

    if usuario_ve_todas_tarefas(user):
        return base

    filtro_resp = _filtro_responsavel(user)
    empresa_ids = _empresa_ids_usuario(user)

    filtro_acesso = Q(empresa__isnull=True)
    if empresa_ids:
        filtro_acesso |= Q(empresa_id__in=empresa_ids)

    filtro_final = filtro_acesso
    if filtro_resp is not None:
        filtro_final |= filtro_resp

    return base.filter(filtro_final)


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


def mensagens_letreiro_usuario(user) -> list[dict]:
    """Textos do letreiro: responsável × empresa × tarefa."""
    hoje = timezone.localdate()
    mensagens: list[dict] = []
    responsavel_padrao = (aliases_responsavel(user) or [''])[0]

    for tarefa in tarefas_vencendo_queryset(user):
        emp = tarefa.empresa_rotulo
        prazo = _rotulo_prazo(hoje, tarefa.previsao_conclusao)
        resp = (tarefa.responsavel or '').strip() or responsavel_padrao or 'Sem responsável'
        hora = f' {tarefa.horario_rotulo}' if tarefa.horario_rotulo else ''
        texto = (
            f'{resp} · {emp} · {tarefa.titulo}{hora} — {prazo} '
            f'(comp. {tarefa.competencia_rotulo})'
        )
        try:
            url = reverse('agendador_tarefas:editar', args=[tarefa.pk])
        except Exception:
            url = ''
        mensagens.append({
            'texto': texto,
            'url': url,
        })
    return mensagens
