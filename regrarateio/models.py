import inspect

from django.db import models
from django.db.models import Q

# Django 5.2+: CheckConstraint(condition=...); antes: check=...
_cc_kw = (
    "condition"
    if "condition" in inspect.signature(models.CheckConstraint.__init__).parameters
    else "check"
)
from socio.models import Socio


class RegraRateio(models.Model):
    MODO_PERCENTUAL = 'P'
    MODO_VALOR = 'V'
    MODO_ALOCACAO_CHOICES = (
        (MODO_PERCENTUAL, 'Percentual fixo'),
        (MODO_VALOR, 'Valor na aplicação'),
    )

    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        related_name='regras_rateio',
        verbose_name='Empresa',
    )
    codigo = models.CharField(verbose_name='Código', max_length=30, blank=True, default='')
    nomedaregra = models.CharField(verbose_name='Descrição da regra', max_length=30)
    rateio = models.CharField(
        verbose_name='Rateio',
        max_length=1,
        default='S',
        choices=(
            ('S', 'SIM'),
            ('N', 'NAO'),
        ),
        help_text='SIM: divide o valor entre sócios. NÃO: não gera lançamentos de rateio.',
    )
    modo_alocacao = models.CharField(
        verbose_name='Modo de alocação',
        max_length=1,
        default=MODO_PERCENTUAL,
        choices=MODO_ALOCACAO_CHOICES,
        help_text=(
            'Percentual fixo: usa % cadastrados nos itens. '
            'Valor na aplicação: informe quanto vai para o sócio manual em cada título; o restante fica com o(s) sócio(s) residual.'
        ),
    )

    class Meta:
        verbose_name = 'Regra de rateio'
        verbose_name_plural = 'Regras de rateio'
        ordering = ['empresa_id', 'nomedaregra']
        indexes = [
            models.Index(fields=['empresa', 'nomedaregra']),
        ]

    def __str__(self):
        if self.codigo:
            return f'{self.codigo} — {self.nomedaregra}'
        return self.nomedaregra


class RegraRateioItem(models.Model):
    TIPO_PERCENTUAL = 'P'
    TIPO_MANUAL = 'M'
    TIPO_RESIDUAL = 'R'
    TIPO_PARTICIPACAO_CHOICES = (
        (TIPO_PERCENTUAL, 'Percentual fixo'),
        (TIPO_MANUAL, 'Valor manual na aplicação'),
        (TIPO_RESIDUAL, 'Residual (restante)'),
    )

    regrarateio = models.ForeignKey(RegraRateio, on_delete=models.DO_NOTHING)
    socios = models.ForeignKey(Socio, on_delete=models.DO_NOTHING)
    percRateio = models.DecimalField(default=0.00, verbose_name="Percentual Rateio", null=False, max_digits=5, decimal_places=2)
    tipo_participacao = models.CharField(
        verbose_name='Tipo de participação',
        max_length=1,
        default=TIPO_PERCENTUAL,
        choices=TIPO_PARTICIPACAO_CHOICES,
    )

    def __str__(self):
        return str(self.regrarateio.nomedaregra) or ''


class LancamentoRateio(models.Model):
    """Linha de rateio gerada a partir de contas a pagar (PGTO, valor negativo) ou a receber (RECEBIMENTO, valor positivo)."""

    TIPO_PGTO = 'PGTO'
    TIPO_RECEBIMENTO = 'RECEBIMENTO'
    TIPO_CHOICES = [
        (TIPO_PGTO, 'Pagamento'),
        (TIPO_RECEBIMENTO, 'Recebimento'),
    ]

    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        verbose_name='Empresa',
        null=True,
        blank=True,
    )
    conta_pagar = models.ForeignKey(
        'contasapagar.ContasaPagar',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lancamentos_rateio',
        verbose_name='Conta a pagar',
    )
    conta_receber = models.ForeignKey(
        'contasareceber.ContaAReceber',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lancamentos_rateio',
        verbose_name='Conta a receber',
    )
    data_pagamento = models.DateField(verbose_name='Data de pagamento / recebimento', null=True, blank=True)
    tipo = models.CharField(verbose_name='Tipo', max_length=20, choices=TIPO_CHOICES)
    descricao = models.CharField(verbose_name='Descrição', max_length=255, blank=True)
    regra_rateio = models.ForeignKey(
        RegraRateio,
        on_delete=models.PROTECT,
        verbose_name='Regra de rateio',
    )
    socio = models.ForeignKey(Socio, on_delete=models.PROTECT, verbose_name='Sócio')
    valor = models.DecimalField(verbose_name='Valor', max_digits=14, decimal_places=2)
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        verbose_name = 'Lançamento de rateio'
        verbose_name_plural = 'Lançamentos de rateio'
        ordering = ['-data_pagamento', '-id']
        constraints = [
            models.CheckConstraint(
                **{
                    _cc_kw: (
                        Q(conta_pagar__isnull=False, conta_receber__isnull=True)
                        | Q(conta_pagar__isnull=True, conta_receber__isnull=False)
                    )
                },
                name='lancamento_rateio_cap_ou_car',
            ),
        ]
        indexes = [
            models.Index(fields=['empresa', '-data_pagamento']),
            models.Index(fields=['conta_pagar']),
            models.Index(fields=['conta_receber']),
        ]

    def __str__(self):
        origem = self.conta_pagar_id or self.conta_receber_id
        return f'{self.get_tipo_display()} #{origem} — {self.socio} — {self.valor}'