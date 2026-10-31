"""Tarefas diárias: backup PostgreSQL → Google Drive (horários configuráveis)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

TITULO_BACKUP_PREFIX = 'Backup PostgreSQL → Google Drive'
TITULO_BACKUP_BANCO = TITULO_BACKUP_PREFIX  # compat. migrations antigas


def titulo_backup_slot(hora: time, pasta: str = 'BKP_SAUDE') -> str:
    return f'{TITULO_BACKUP_PREFIX} ({pasta} · {hora.strftime("%H:%M")})'


def _config_ou_padrao():
    try:
        from accounts.backup_config import (
            descricao_tarefa_backup,
            horarios_backup_ativos,
            obter_config_backup,
        )

        config = obter_config_backup()
        return config, horarios_backup_ativos(config), descricao_tarefa_backup(config)
    except Exception:
        config = None
        slots = [time(12, 0), time(18, 0)]
        descricao = (
            'Backup automático do PostgreSQL para o Google Drive (pasta BKP_SAUDE). '
            'Configure em Admin → Backup → Agendamento.'
        )
        return config, slots, descricao


def gerar_tarefas_backup_banco(*, inicio: date, fim: date) -> list[dict]:
    config, slots, descricao = _config_ou_padrao()
    pasta = (getattr(config, 'drive_pasta_nome', None) or 'BKP_SAUDE') if config else 'BKP_SAUDE'
    responsavel = (getattr(config, 'responsavel_tarefa', None) or 'saude') if config else 'saude'
    if config and not config.gerar_tarefas_agendador:
        return []

    tarefas: list[dict] = []
    dia = inicio
    while dia <= fim:
        for slot in slots:
            inicio_dt = datetime.combine(dia, slot)
            fim_dt = inicio_dt + timedelta(minutes=30)
            tarefas.append(
                {
                    'titulo': titulo_backup_slot(slot, pasta=pasta),
                    'descricao': descricao,
                    'data': dia,
                    'previsao_conclusao': dia,
                    'competencia_mes': dia.month,
                    'competencia_ano': dia.year,
                    'hora_inicio': slot,
                    'hora_fim': fim_dt.time(),
                    'responsavel': responsavel,
                }
            )
        dia += timedelta(days=1)
    return tarefas


def criar_tarefas_backup_banco_agenda(TarefaAgendada, *, inicio: date, fim: date) -> int:
    criadas = 0
    for item in gerar_tarefas_backup_banco(inicio=inicio, fim=fim):
        _, created = TarefaAgendada.objects.get_or_create(
            empresa=None,
            titulo=item['titulo'],
            data=item['data'],
            defaults={
                'descricao': item['descricao'],
                'previsao_conclusao': item['previsao_conclusao'],
                'competencia_mes': item['competencia_mes'],
                'competencia_ano': item['competencia_ano'],
                'hora_inicio': item['hora_inicio'],
                'hora_fim': item['hora_fim'],
                'responsavel': item['responsavel'],
            },
        )
        if created:
            criadas += 1
    return criadas


def remover_tarefas_backup_banco_agenda(TarefaAgendada) -> int:
    deleted, _ = (
        TarefaAgendada.objects.filter(empresa_id__isnull=True)
        .filter(titulo__startswith=TITULO_BACKUP_PREFIX)
        .delete()
    )
    return deleted


def sincronizar_tarefas_backup_banco_agenda(
    TarefaAgendada=None,
    *,
    inicio: date | None = None,
    fim: date | None = None,
) -> int:
    if TarefaAgendada is None:
        from agendador_tarefas.models import TarefaAgendada as TA

        TarefaAgendada = TA

    try:
        from accounts.backup_config import obter_config_backup

        config = obter_config_backup()
        dias = config.dias_tarefas_frente or 365
    except Exception:
        dias = 365

    hoje = date.today()
    inicio = inicio or hoje
    fim = fim or hoje + timedelta(days=dias)

    remover_tarefas_backup_banco_agenda(TarefaAgendada)
    return criar_tarefas_backup_banco_agenda(TarefaAgendada, inicio=inicio, fim=fim)
