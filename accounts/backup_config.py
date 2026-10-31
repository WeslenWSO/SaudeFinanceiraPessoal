"""Leitura da configuração de backup (banco + helpers para agendador e cron)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

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
) -> tuple[time, BackupExecucaoAgendada] | None:
    """
    Reserva o slot do cron (hora local, minuto 0–29).
    Reexecuta se a tentativa anterior falhou (sucesso=False).
    """
    config = obter_config_backup()
    if not config.backup_automatico_ativo:
        return None
    agora = timezone.localtime(agora or timezone.now())
    if agora.minute >= 30:
        return None
    for slot in horarios_backup_ativos(config):
        if agora.hour != slot.hour:
            continue
        row = BackupExecucaoAgendada.objects.filter(
            data=agora.date(),
            hora=slot.hour,
        ).first()
        if row and row.sucesso:
            return None
        if not row:
            row = BackupExecucaoAgendada.objects.create(
                data=agora.date(),
                hora=slot.hour,
                origem='cron',
                sucesso=False,
            )
        return slot, row
    return None
