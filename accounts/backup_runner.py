"""Executa backup + upload Drive e registra resultado (cron, manual ou tela admin)."""

from __future__ import annotations

from django.utils import timezone

from accounts.backup_banco import criar_backup_completo
from accounts.backup_config import slot_backup_para_executar_agora
from accounts.backup_google_drive import drive_configurado, enviar_backup_info_para_drive
from accounts.models import BackupExecucaoAgendada


def _registrar_execucao(
    execucao: BackupExecucaoAgendada | None,
    *,
    sucesso: bool,
    mensagem: str,
    arquivo_nome: str = '',
    drive_file_id: str = '',
    origem: str = '',
) -> BackupExecucaoAgendada:
    if execucao is None:
        agora = timezone.localtime()
        execucao = BackupExecucaoAgendada.objects.create(
            data=agora.date(),
            hora=agora.hour,
            origem=origem or 'manual',
        )
    execucao.sucesso = sucesso
    execucao.mensagem = (mensagem or '')[:2000]
    execucao.arquivo_nome = (arquivo_nome or '')[:255]
    execucao.drive_file_id = (drive_file_id or '')[:128]
    if origem:
        execucao.origem = origem[:20]
    execucao.save(
        update_fields=[
            'sucesso',
            'mensagem',
            'arquivo_nome',
            'drive_file_id',
            'origem',
        ]
    )
    return execucao


def executar_backup_google_drive(
    *,
    modo: str = 'manual',
) -> dict:
    """
    modo:
      - manual / forcar: sempre executa
      - agendado: só no horário configurado (cron Render)
    """
    execucao: BackupExecucaoAgendada | None = None
    slot = None

    if modo == 'agendado':
        reserva = slot_backup_para_executar_agora()
        if reserva is None:
            return {
                'ok': False,
                'pulou': True,
                'mensagem': 'Fora do horário de backup agendado ou slot já concluído hoje.',
            }
        slot, execucao = reserva

    try:
        info = criar_backup_completo()
        arquivo = info.get('arquivo') or ''
        msg_local = (
            f"Backup local: {arquivo} ({info.get('formato')}, {info.get('tamanho')} bytes)"
        )
        extras = info.get('extras') or []
        if extras:
            msg_local += ' + ' + ', '.join(e['arquivo'] for e in extras)

        if not drive_configurado():
            _registrar_execucao(
                execucao,
                sucesso=False,
                mensagem=(
                    msg_local
                    + ' — Google Drive NÃO configurado neste serviço '
                    '(BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON).'
                ),
                arquivo_nome=arquivo,
                origem=modo if modo != 'agendado' else 'cron',
            )
            return {
                'ok': False,
                'pulou': False,
                'mensagem': msg_local,
                'drive_ok': False,
                'arquivo': arquivo,
            }

        uploads = enviar_backup_info_para_drive(info)
        nomes = ', '.join(u.get('name') or '?' for u in uploads)
        ids = ', '.join(u.get('file_id') or '?' for u in uploads)
        msg = f'{msg_local} — Enviado ao Drive ({len(uploads)} arquivo(s)): {nomes} (ids: {ids})'
        _registrar_execucao(
            execucao,
            sucesso=True,
            mensagem=msg,
            arquivo_nome=arquivo,
            drive_file_id=(uploads[0].get('file_id') if uploads else '') or '',
            origem=modo if modo != 'agendado' else 'cron',
        )
        return {
            'ok': True,
            'pulou': False,
            'mensagem': msg,
            'drive_ok': True,
            'arquivo': arquivo,
            'drive_file_id': uploads[0].get('file_id') if uploads else None,
            'slot': slot.strftime('%H:%M') if slot else None,
        }
    except Exception as exc:
        _registrar_execucao(
            execucao,
            sucesso=False,
            mensagem=str(exc),
            origem=modo if modo != 'agendado' else 'cron',
        )
        raise
