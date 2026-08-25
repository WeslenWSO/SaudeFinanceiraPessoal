from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from empresa.models import Empresa
from notasfiscais.models import NotaFiscalServico
from categoria.models import Categoria
from regrarateio.models import RegraRateio
from extrato.models import ContaBancaria

class ContaAReceber(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
        ('cancelado', 'Cancelado'),
        ('vencido', 'Vencido'),
        ('cartao', 'Cartão'),
    ]

    # Empresa
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')

    # Nota Fiscal
    nota = models.ForeignKey(NotaFiscalServico, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Nota Fiscal')

    # Sócio (espelha a NF quando vinculada; permite título sem NF)
    socio = models.ForeignKey(
        'socio.Socio',
        verbose_name='Sócio responsável',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Cliente (herdado da nota)
    cliente = models.CharField(verbose_name='Cliente', max_length=200)
    cnpj_cpf = models.CharField(verbose_name='CNPJ/CPF', max_length=18, blank=True, null=True)

    # Datas
    data_emissao = models.DateField(verbose_name='Data de Emissão', default=timezone.now)
    data_vencimento = models.DateField(verbose_name='Data de Vencimento')
    data_recebimento = models.DateField(verbose_name='Data do Recebimento', null=True, blank=True)

    # Valores
    valor_a_receber = models.DecimalField(verbose_name='Valor a Receber', max_digits=10, decimal_places=2)

    # Parcela
    parcela = models.CharField(verbose_name='Parcela', max_length=20, default='1/1')

    # Documento
    doc = models.CharField(verbose_name='Documento', max_length=50, blank=True, null=True)

    # Forma de Pagamento
    forma_pagamento = models.ForeignKey('cobranca.Cobranca', verbose_name='Cobrança', on_delete=models.SET_NULL, null=True, blank=True)

    # Autorização
    autorizacao = models.CharField(verbose_name='Autorização', max_length=100, blank=True, null=True)

    # Observações
    observacao = models.TextField(verbose_name='Observação', blank=True, null=True)

    # Categoria
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Categoria')

    # Regra de Rateio
    regra_rateio = models.ForeignKey(RegraRateio, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Regra de Rateio')

    # Recebimento
    conta_banco = models.ForeignKey(ContaBancaria, verbose_name='Conta/Banco', on_delete=models.SET_NULL, null=True, blank=True)
    valor_recebido = models.DecimalField(verbose_name='Valor Recebido', max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    desconto = models.DecimalField(verbose_name='Desconto', max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    juros = models.DecimalField(verbose_name='Juros', max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    tarifas = models.DecimalField(verbose_name='Tarifas', max_digits=10, decimal_places=2, null=True, blank=True, default=0)

    conta_azul_parcela_id = models.CharField(
        max_length=36,
        blank=True,
        default='',
        db_index=True,
        verbose_name='ID parcela Conta Azul',
    )

    # Status
    status = models.CharField(verbose_name='Status', max_length=20, choices=STATUS_CHOICES, default='pendente')

    # Timestamps
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Conta a Receber'
        verbose_name_plural = 'Contas a Receber'
        ordering = ['-data_vencimento', '-data_emissao']

    def __str__(self):
        numero_nota = self.nota.numero_nota if self.nota else "Sem Nota"
        return f"Conta {numero_nota} - {self.cliente} - R$ {self.valor_a_receber}"

    def get_saldo_nominal_para_quitacao(self):
        """Valor da parcela − já recebido (soma das baixas), sem atalho por status.
        Usado para saber se o título está quitado com desconto/juros/tarifa."""
        rec = self.valor_recebido or Decimal('0')
        v = self.valor_a_receber or Decimal('0')
        return max(v - rec, Decimal('0'))

    def get_saldo_nominal_pendente(self):
        """Saldo nominal para exibição: zero se pago; em cartão parcial mostra o que falta."""
        if self.status == 'pago':
            return Decimal('0')
        if self.status == 'cartao':
            return self.get_saldo_nominal_para_quitacao()
        return self.get_saldo_nominal_para_quitacao()

    def get_valor_liquido_restante(self):
        """Saldo da quitação: valor_a_receber − valor_recebido − desconto − tarifa + juros.

        Em aberto na parcela (sem «já recebido»), equivale a: saldo nominal pendente − desconto − tarifa + juros − valor_recebido.
        Quitado quando ≈ 0, ou seja, na baixa: saldo nominal − desconto − tarifa + juros = valor recebido (ex.: 350−0−100+0=250).
        Não usar max(V−R, 0): se R > V (ex.: crédito cobre face + juros), o teto zerava (V−R)
        e sobrava só +juros, impedindo status pago."""
        v = self.valor_a_receber or Decimal('0')
        r = self.valor_recebido or Decimal('0')
        d = self.desconto or Decimal('0')
        t = self.tarifas or Decimal('0')
        j = self.juros or Decimal('0')
        return v - r - d - t + j

    def get_total_liquido_listagem(self):
        """Total líquido na listagem: se pago (= recebido), valor recebido; senão valor a receber − tarifa − desconto + juros."""
        if self.status == 'pago':
            return self.valor_recebido or Decimal('0')
        if self.status == 'cartao':
            return self.valor_recebido or Decimal('0')
        v = self.valor_a_receber or Decimal('0')
        t = self.tarifas or Decimal('0')
        d = self.desconto or Decimal('0')
        j = self.juros or Decimal('0')
        return v - t - d + j

    def get_valor_total_com_ajustes(self):
        """Compatível com listagens: mesmo valor que o líquido em aberto."""
        return self.get_valor_liquido_restante()

    def get_valor_pendente(self):
        """Valor ainda em aberto (líquido), nunca negativo."""
        if self.status == 'pago':
            return Decimal('0')
        lr = self.get_valor_liquido_restante()
        return max(lr, Decimal('0'))

    def is_pago(self):
        """Quitada quando o líquido restante é zero ou negativo (mesma tolerância do recálculo por baixas)."""
        if self.status == 'pago':
            return True
        return self.get_valor_liquido_restante() <= Decimal('0.02')

    def is_vencida(self):
        """Verifica se a conta está vencida"""
        if self.data_recebimento or self.status == 'pago':
            return False
        if not self.data_vencimento:
            return False
        return timezone.now().date() > self.data_vencimento

    @property
    def dias_atraso(self):
        """Retorna o número de dias em atraso"""
        if self.is_vencida():
            return (timezone.now().date() - self.data_vencimento).days
        return 0


class BaixaContaAReceber(models.Model):
    """Modelo para registrar as baixas/recebimentos de contas a receber"""

    TIPO_BAIXA_CHOICES = [
        ('parcial', 'Baixa Parcial'),
        ('total', 'Baixa Total'),
    ]

    # Relacionamento com conta a receber
    conta_a_receber = models.ForeignKey(ContaAReceber, on_delete=models.CASCADE, verbose_name='Conta a Receber',
                                       related_name='baixas')

    # Empresa (para facilitar consultas)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')

    # Dados do recebimento
    data_recebimento = models.DateField(verbose_name='Data do Recebimento', default=timezone.now)
    valor_recebido = models.DecimalField(verbose_name='Valor Recebido', max_digits=10, decimal_places=2)

    # Ajustes
    desconto = models.DecimalField(verbose_name='Desconto', max_digits=10, decimal_places=2, default=0)
    juros = models.DecimalField(verbose_name='Juros', max_digits=10, decimal_places=2, default=0)
    tarifas = models.DecimalField(verbose_name='Tarifas', max_digits=10, decimal_places=2, default=0)

    # Conta bancária onde foi depositado
    conta_banco = models.ForeignKey(ContaBancaria, verbose_name='Conta Bancária', on_delete=models.SET_NULL, null=True, blank=True)

    # Tipo de baixa
    tipo_baixa = models.CharField(verbose_name='Tipo de Baixa', max_length=10, choices=TIPO_BAIXA_CHOICES, default='total')

    # Observações
    observacao = models.TextField(verbose_name='Observação', blank=True, null=True)

    # Timestamps
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Baixa de Conta a Receber'
        verbose_name_plural = 'Baixas de Contas a Receber'
        ordering = ['-data_recebimento', '-data_criacao']

    def __str__(self):
        return f"Baixa {self.conta_a_receber} - R$ {self.valor_recebido} em {self.data_recebimento}"

    def valor_total_com_ajustes(self):
        """Líquido creditado no banco (bate com o extrato): valor recebido + juros − desconto.

        A tarifa não entra aqui: o campo «valor recebido» na baixa é o crédito líquido no extrato;
        a tarifa compõe só o lado do título (saldo nominal − … − tarifa + juros = valor recebido)."""
        vr = self.valor_recebido or Decimal('0')
        j = self.juros or Decimal('0')
        d = self.desconto or Decimal('0')
        return vr + j - d

    def get_valor_credito_extrato(self):
        """Crédito conforme linhas do extrato vinculadas à baixa; senão VR + juros − desconto."""
        movs = list(self.extrato_movimentos.all())
        if movs:
            return sum(Decimal(str(m.valor or 0)) for m in movs)
        vr = self.valor_recebido or Decimal('0')
        j = self.juros or Decimal('0')
        d = self.desconto or Decimal('0')
        return vr + j - d

    @classmethod
    def atualizar_totais_na_conta(cls, conta):
        """Recalcula na ContaAReceber: valor recebido, desconto, juros e tarifas (soma das baixas) e status."""
        pk = conta.pk if hasattr(conta, 'pk') else conta
        conta = ContaAReceber.objects.get(pk=pk)

        dec_field = DecimalField(max_digits=14, decimal_places=2)
        baixas = cls.objects.filter(conta_a_receber_id=pk)
        if not baixas.exists():
            conta.valor_recebido = Decimal('0')
            conta.desconto = Decimal('0')
            conta.juros = Decimal('0')
            conta.tarifas = Decimal('0')
            conta.data_recebimento = None
            hoje = timezone.now().date()
            if conta.data_vencimento and hoje > conta.data_vencimento:
                conta.status = 'vencido'
            else:
                conta.status = 'pendente'
            conta.save()
            return

        agg = baixas.aggregate(
            tr=Coalesce(Sum('valor_recebido'), Value(0), output_field=dec_field),
            td=Coalesce(Sum('desconto'), Value(0), output_field=dec_field),
            tj=Coalesce(Sum('juros'), Value(0), output_field=dec_field),
            tt=Coalesce(Sum('tarifas'), Value(0), output_field=dec_field),
        )

        conta.valor_recebido = Decimal(str(agg['tr']))
        conta.desconto = Decimal(str(agg['td']))
        conta.juros = Decimal(str(agg['tj']))
        conta.tarifas = Decimal(str(agg['tt']))

        ultima_baixa = baixas.order_by('-data_recebimento', '-id').first()
        conta.data_recebimento = ultima_baixa.data_recebimento if ultima_baixa else None

        liquido = conta.get_valor_liquido_restante()
        if liquido <= Decimal('0.02'):
            conta.status = 'pago'
        else:
            hoje = timezone.now().date()
            if conta.data_vencimento and hoje > conta.data_vencimento:
                conta.status = 'vencido'
            else:
                conta.status = 'pendente'

        conta.save()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.atualizar_totais_na_conta(self.conta_a_receber)

    def delete(self, *args, **kwargs):
        conta = self.conta_a_receber
        super().delete(*args, **kwargs)
        type(self).atualizar_totais_na_conta(conta)
