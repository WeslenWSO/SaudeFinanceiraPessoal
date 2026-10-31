"""Leitura da configuração de backup (banco + helpers para agendador e cron)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db import IntegrityError
from django.utils import timezone

from accounts.models import BackupBancoConfig, BackupExecucaoAgendada


def obter_config_backup() -> BackupBancoConfig:
    obj = BackupBancoConfig.objects.order_by('pk').first()
    if obj:
        return obj
    return BackupBancoConfig.objects.create()


def horarios_backup_ativos(config: BackupBancoConfig | None = None) -> list[time]:
    config = config or obter_config_backup()
    slots: list[time] = []
    if config.horario_1_ativo:
        slots.append(config.horario_1)
    if config.horario_2_ativo:
        slots.append(config.horario_2)
    return sorted(set(slots))


def drive_folder_id_configurado() -> str:
    return (obter_config_backup().drive_folder_id or '').strip()


def descricao_tarefa_backup(config: BackupBancoConfig) -> str:
    pasta = config.drive_pasta_nome or 'BKP_SAUDE'
    folder = (config.drive_folder_id or '').strip()
    horarios = ', '.join(h.strftime('%H:%M') for h in horarios_backup_ativos(config))
    return (
        f'Backup automático do PostgreSQL para a pasta {pasta} no Google Drive '
        f'(folder id {folder}). Horários (fuso do sistema): {horarios or "—"}. '
        'Cron: python manage.py backup_banco_google_drive --agendado. '
        'Manual: python manage.py backup_banco_google_drive'
    )


def slot_backup_para_executar_agora(
    *,
    agora: datetime | None = None,
) -> time | None:
    """
    Retorna o horário configurado cujo slot deve rodar nesta execução do cron
    (mesma hora local, minutos 0–29).
    """
    config = obter_config_backup()
    if not config.backup_automatico_ativo:
        return None
    agora = timezone.localtime(agora or timezone.now())
    if agora.minute >= 30:
        return None
    for slot in horarios_backup_ativos(config):
        if agora.hour == slot.hour:
            try:
                BackupExecucaoAgendada.objects.create(
                    data=agora.date(),
                    hora=slot.hour,
                )
            except IntegrityError:
                return None
            return slot
    return None
