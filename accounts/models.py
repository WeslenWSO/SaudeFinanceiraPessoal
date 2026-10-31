from datetime import time

from django.db import models


class BackupBancoConfig(models.Model):
    """Configuração única (pk=1): horários, pasta Drive e lembretes no agendador."""

    drive_folder_id = models.CharField(
        max_length=128,
        default='1f6ULWD8aAPS5gfG7mGwY2GbG_HrQgz4y',
        verbose_name='ID da pasta no Google Drive',
        help_text='Ex.: link drive.google.com/.../folders/ESTE_ID',
    )
    drive_pasta_nome = models.CharField(
        max_length=120,
        default='BKP_SAUDE',
        blank=True,
        verbose_name='Nome da pasta (referência)',
    )
    horario_1 = models.TimeField(default=time(12, 0), verbose_name='Horário 1')
    horario_1_ativo = models.BooleanField(default=True, verbose_name='Ativar horário 1')
    horario_2 = models.TimeField(default=time(18, 0), verbose_name='Horário 2')
    horario_2_ativo = models.BooleanField(default=True, verbose_name='Ativar horário 2')
    backup_automatico_ativo = models.BooleanField(
        default=True,
        verbose_name='Backup automático (cron)',
    )
    gerar_tarefas_agendador = models.BooleanField(
        default=True,
        verbose_name='Gerar lembretes no agendador de tarefas',
    )
    responsavel_tarefa = models.CharField(
        max_length=120,
        default='saude',
        verbose_name='Responsável das tarefas',
    )
    dias_tarefas_frente = models.PositiveSmallIntegerField(
        default=365,
        verbose_name='Dias de tarefas à frente',
    )

    class Meta:
        verbose_name = 'Configuração de backup do banco'
        verbose_name_plural = 'Configuração de backup do banco'

    def __str__(self) -> str:
        return 'Configuração de backup'


class BackupExecucaoAgendada(models.Model):
    """Histórico de execuções automáticas e manuais de backup."""

    data = models.DateField(db_index=True)
    hora = models.PositiveSmallIntegerField(
        help_text='Hora local (0–23) do slot configurado.',
    )
    executado_em = models.DateTimeField(auto_now_add=True)
    sucesso = models.BooleanField(default=False)
    mensagem = models.TextField(blank=True, default='')
    arquivo_nome = models.CharField(max_length=255, blank=True, default='')
    drive_file_id = models.CharField(max_length=128, blank=True, default='')
    origem = models.CharField(
        max_length=20,
        blank=True,
        default='cron',
        help_text='cron, manual ou forcar',
    )

    class Meta:
        verbose_name = 'Execução de backup agendada'
        verbose_name_plural = 'Execuções de backup agendadas'
        constraints = [
            models.UniqueConstraint(
                fields=['data', 'hora'],
                name='accounts_backup_exec_data_hora_uniq',
            ),
        ]
