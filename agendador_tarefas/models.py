from django.conf import settings
from django.db import models

from empresa.models import Empresa


class TarefaAgendada(models.Model):
    STATUS_PENDENTE = 'pendente'
    STATUS_CONCLUIDO = 'concluido'
    STATUS_COM_SUPERVISOR = 'com_supervisor'

    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_CONCLUIDO, 'Concluído'),
        (STATUS_COM_SUPERVISOR, 'Com Supervisor'),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='tarefas_agendadas',
        verbose_name='Empresa',
        null=True,
        blank=True,
    )
    competencia_mes = models.PositiveSmallIntegerField(
        verbose_name='Competência (mês)',
        db_index=True,
    )
    competencia_ano = models.PositiveSmallIntegerField(
        verbose_name='Competência (ano)',
        db_index=True,
    )
    data = models.DateField(verbose_name='Data', db_index=True)
    previsao_conclusao = models.DateField(verbose_name='Previsão de conclusão')
    hora_inicio = models.TimeField(
        verbose_name='Hora início',
        null=True,
        blank=True,
    )
    hora_fim = models.TimeField(
        verbose_name='Hora fim',
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENTE,
        verbose_name='Status',
        db_index=True,
    )
    responsavel = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Responsável',
    )
    titulo = models.CharField(max_length=200, verbose_name='Título')
    descricao = models.TextField(blank=True, default='', verbose_name='Descrição')
    data_conclusao = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data da conclusão',
    )
    concluido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tarefas_concluidas',
        verbose_name='Quem concluiu',
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tarefas_criadas',
        verbose_name='Quem criou',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tarefa agendada'
        verbose_name_plural = 'Tarefas agendadas'
        ordering = ['previsao_conclusao', 'titulo']
        indexes = [
            models.Index(fields=['empresa', 'competencia_ano', 'competencia_mes']),
        ]

    def __str__(self):
        return f'{self.titulo} — {self.competencia_rotulo}'

    @property
    def competencia_rotulo(self) -> str:
        return f'{self.competencia_mes:02d}/{self.competencia_ano}'

    @property
    def is_geral(self) -> bool:
        return self.empresa_id is None

    @property
    def empresa_rotulo(self) -> str:
        if not self.empresa_id:
            return 'Geral'
        return self.empresa.nome_fantasia or self.empresa.razao

    @property
    def horario_rotulo(self) -> str:
        if self.hora_inicio and self.hora_fim:
            return f'{self.hora_inicio.strftime("%H:%M")}–{self.hora_fim.strftime("%H:%M")}'
        if self.hora_inicio:
            return self.hora_inicio.strftime('%H:%M')
        return ''

    @property
    def status_badge(self) -> str:
        mapa = {
            self.STATUS_PENDENTE: 'warning',
            self.STATUS_CONCLUIDO: 'success',
            self.STATUS_COM_SUPERVISOR: 'info',
        }
        return mapa.get(self.status, 'secondary')


class TarefaResponsavelLog(models.Model):
    """Histórico de passagem de responsável da tarefa."""

    tarefa = models.ForeignKey(
        TarefaAgendada,
        on_delete=models.CASCADE,
        related_name='logs_responsavel',
        verbose_name='Tarefa',
    )
    responsavel_anterior = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Responsável anterior',
    )
    responsavel_novo = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Responsável novo',
    )
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs_passagem_tarefa',
        verbose_name='Quem passou',
    )
    alterado_em = models.DateTimeField(auto_now_add=True, verbose_name='Quando')
    observacao = models.TextField(blank=True, default='', verbose_name='Observação')

    class Meta:
        verbose_name = 'Log de responsável'
        verbose_name_plural = 'Logs de responsável'
        ordering = ['-alterado_em']

    def __str__(self):
        return (
            f'{self.tarefa.titulo}: '
            f'"{self.responsavel_anterior or "—"}" → "{self.responsavel_novo or "—"}"'
        )


def registrar_passagem_responsavel(
    tarefa: TarefaAgendada,
    responsavel_anterior: str,
    responsavel_novo: str,
    usuario,
    *,
    observacao: str = '',
) -> TarefaResponsavelLog | None:
    ant = (responsavel_anterior or '').strip()
    novo = (responsavel_novo or '').strip()
    if ant == novo:
        return None
    return TarefaResponsavelLog.objects.create(
        tarefa=tarefa,
        responsavel_anterior=ant,
        responsavel_novo=novo,
        alterado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
        observacao=(observacao or '').strip(),
    )
