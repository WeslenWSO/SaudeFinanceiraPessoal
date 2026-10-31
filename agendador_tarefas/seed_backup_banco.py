"""Tarefa diária: backup PostgreSQL enviado ao Google Drive (pasta BKP_SAUDE)."""

from __future__ import annotations

from datetime import date, time, timedelta

TITULO_BACKUP_BANCO = 'Backup PostgreSQL → Google Drive (BKP_SAUDE)'


def gerar_tarefas_backup_banco(*, inicio: date, fim: date) -> list[dict]:
    """Segunda a domingo — lembrete + comando automático no Render cron."""
    descricao = (
        'Backup automático do PostgreSQL (Render) para a pasta '
        'BKP_SAUDE no Google Drive (weslensioliveira@gmail.com). '
        'Cron Render: backup_banco_google_drive. Manual: '
        'python manage.py backup_banco_google_drive'
    )
    tarefas: list[dict] = []
    dia = inicio
    while dia <= fim:
        tarefas.append(
            {
                'titulo': TITULO_BACKUP_BANCO,
                'descricao': descricao,
                'data': dia,
                'previsao_conclusao': dia,
                'competencia_mes': dia.month,
                'competencia_ano': dia.year,
                'hora_inicio': time(2, 0),
                'hora_fim': time(2, 30),
                'responsavel': 'saude',
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
