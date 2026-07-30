from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from empresa.models import Empresa


class Opcartao(models.Model):
    tband = models.CharField(verbose_name='tband', max_length=2)
    descricao = models.CharField(verbose_name='Descricao', max_length=50)

    def __str__(self):
        return f'{self.tband} {self.descricao}'


class CartaoCredito(models.Model):
    BANDEIRA_CHOICES = [
        ('VISA', 'Visa'),
        ('MASTERCARD', 'Mastercard'),
        ('ELO', 'Elo'),
        ('AMEX', 'American Express'),
        ('HIPERCARD', 'Hipercard'),
        ('OUTRA', 'Outra'),
    ]
    BANCO_CHOICES = [
        ('SICREDI', 'Sicredi'),
        ('SICOOB', 'Sicoob'),
        ('OUTRO', 'Outro'),
    ]

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name='cartoes_credito',
    )
    descricao = models.CharField(max_length=80, verbose_name='Descrição')
    banco = models.CharField(max_length=20, choices=BANCO_CHOICES, default='SICREDI')
    bandeira = models.CharField(max_length=20, choices=BANDEIRA_CHOICES, default='VISA')
    final_cartao = models.CharField(max_length=8, blank=True, default='', verbose_name='Final do cartão')
    dia_fechamento_fatura = models.PositiveSmallIntegerField(
        verbose_name='Dia do fechamento da fatura',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text='Dia do mês em que a fatura fecha (ex.: 20).',
    )
    dia_vencimento_fatura = models.PositiveSmallIntegerField(
        verbose_name='Dia do vencimento da fatura',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text='Dia do mês em que a fatura vence (ex.: 3).',
    )
    limite = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Limite do cartão',
        help_text='Limite total de crédito do cartão.',
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['descricao', 'id']
        verbose_name = 'Cartão de crédito'
        verbose_name_plural = 'Cartões de crédito'

    def __str__(self):
        final = f' final {self.final_cartao}' if self.final_cartao else ''
        return f'{self.descricao} — {self.get_bandeira_display()}{final}'


class FaturaCartaoCredito(models.Model):
    BANCO_CHOICES = [
        ('SICREDI', 'Sicredi'),
        ('SICOOB', 'Sicoob'),
        ('OUTRO', 'Outro'),
    ]

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name='faturas_cartao',
    )
    cartao = models.ForeignKey(
        CartaoCredito, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='faturas',
    )
    banco = models.CharField(max_length=20, choices=BANCO_CHOICES, default='SICREDI')
    titular = models.CharField(max_length=120, blank=True, default='')
    bandeira = models.CharField(max_length=30, blank=True, default='')
    cartao_final = models.CharField(max_length=8, blank=True, default='')
    referencia_mes = models.CharField(max_length=30, blank=True, default='')
    vencimento = models.DateField(null=True, blank=True)
    total_fatura = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    arquivo_nome = models.CharField(max_length=255, blank=True, default='')
    perfil_consumo = models.JSONField(default=list, blank=True)
    conta_cartao = models.CharField(max_length=30, blank=True, default='', verbose_name='Conta cartão')
    cartoes_resumo = models.JSONField(default=list, blank=True, verbose_name='Resumo por cartão')
    importado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-vencimento', '-id']
        verbose_name = 'Fatura de cartão'
        verbose_name_plural = 'Faturas de cartão'

    def __str__(self):
        ref = self.referencia_mes or (self.vencimento.strftime('%m/%Y') if self.vencimento else '')
        return f'Fatura {self.banco} {ref} — R$ {self.total_fatura}'


class ItemFaturaCartao(models.Model):
    TIPO_CHOICES = [
        ('compra', 'Compra'),
        ('pagamento', 'Pagamento'),
        ('iof', 'IOF'),
    ]

    fatura = models.ForeignKey(
        FaturaCartaoCredito, on_delete=models.CASCADE, related_name='itens',
    )
    data = models.DateField(null=True, blank=True)
    hora = models.CharField(max_length=8, blank=True, default='')
    cartao_portador = models.CharField(max_length=120, blank=True, default='')
    cartao_final = models.CharField(max_length=8, blank=True, default='')
    cidade = models.CharField(max_length=80, blank=True, default='')
    tipo_compra = models.CharField(max_length=20, blank=True, default='')
    descricao = models.CharField(max_length=255, blank=True, default='')
    parcela = models.CharField(max_length=10, blank=True, default='')
    categoria = models.CharField(max_length=30, blank=True, default='')
    valor = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='compra')

    class Meta:
        ordering = ['data', 'hora', 'id']
        verbose_name = 'Item da fatura'
        verbose_name_plural = 'Itens da fatura'

    def __str__(self):
        return f'{self.data} {self.descricao} R$ {self.valor}'
