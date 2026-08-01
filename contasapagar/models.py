from decimal import Decimal

from django.db import models
from categoria.models import Categoria
from cobranca.models import Cobranca
from empresa.models import Empresa
from extrato.models import ContaBancaria
from fornecedor.models import Fornecedor
from regrarateio.models import RegraRateio


class ContasaPagar(models.Model):
    # Empresa
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    
    dtEmissao = models.DateField(verbose_name='Data de Emissao', null=True, blank=True)
    fornecedor = models.ForeignKey(Fornecedor, verbose_name='Fornecedor', on_delete=models.DO_NOTHING)
    descricao = models.CharField(verbose_name='Descricao', max_length=100 )
    numdoc = models.CharField(verbose_name='Numero do Documento', max_length=15 )
    valorDoc = models.DecimalField(verbose_name='Valor do Documento', max_digits=12, decimal_places=2)
    categoria = models.ForeignKey(Categoria, verbose_name='Categoria', on_delete=models.DO_NOTHING)
    parcela = models.CharField(verbose_name='Numero de Parcela', max_length=2 )
   
    
    dtvenc = models.DateField(verbose_name='Data de Vencimento', null=True, blank=True)
    cobranca = models.ForeignKey(Cobranca, verbose_name='Cobrança / Forma de Pagto', on_delete=models.DO_NOTHING)
    conta_banco = models.ForeignKey(ContaBancaria, verbose_name='Conta', on_delete=models.DO_NOTHING)
    
    dtPag = models.DateField(verbose_name='Data de Pagamento', null=True, blank=True)
    valorPago = models.DecimalField(verbose_name='Valor Pago', default=0, max_digits=12, decimal_places=2)
    juros = models.DecimalField(verbose_name='Valor do Juros', default=0,max_digits=12, decimal_places=2)
    multa = models.DecimalField(verbose_name='Valor da Multa',default=0, max_digits=12, decimal_places=2)
    desconto = models.DecimalField(verbose_name='Valor do Desconto',default=0, max_digits=12, decimal_places=2) 
    
    
    conta_azul_parcela_id = models.CharField(
        max_length=36,
        blank=True,
        default='',
        db_index=True,
        verbose_name='ID parcela Conta Azul',
    )

    obs = models.CharField(verbose_name='obs', max_length=250)
    rateio = models.ForeignKey(RegraRateio, verbose_name='Rateio', on_delete=models.DO_NOTHING, null=True, blank=True)
    nossonumero = models.CharField(verbose_name='Nosso Numero', max_length=15 )
    nsu = models.CharField(verbose_name='Numero de Autorizacao do Cartao', max_length=15 )
    # anexo =
   
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
        ('cancelado', 'Cancelado'),
        ('vencido', 'Vencido'),
    ]

    # Campo status adicionado
    status = models.CharField(verbose_name='Status', max_length=20, choices=STATUS_CHOICES, default='pendente')

    # Campo CPF/CNPJ
    cpf_cnpj = models.CharField(verbose_name='CPF/CNPJ', max_length=18, blank=True, null=True)

    def __str__(self):
        return f'{self.descricao} {self.cobranca.descricao}'

    def get_valor_pendente(self):
        """Retorna o valor pendente de pagamento"""
        if self.status == 'pago':
            return 0
        valor_total = self.get_valor_total_com_ajustes()
        if self.valorPago:
            pendente = valor_total - self.valorPago
            return max(pendente, 0)
        return valor_total

    def get_valor_total_com_ajustes(self):
        """Retorna o valor total: VALOR DOC + JUROS + MULTA - DESCONTO (tudo em Decimal)."""
        def _d(x):
            if x is None:
                return Decimal('0')
            if isinstance(x, Decimal):
                return x
            return Decimal(str(x))

        return _d(self.valorDoc) + _d(self.juros) + _d(self.multa) - _d(self.desconto)

    def is_pago(self):
        """Verifica se a conta está paga"""
        if self.status == 'pago':
            return True
        valor_total = self.get_valor_total_com_ajustes()
        return self.valorPago and self.valorPago >= valor_total

    def is_vencida(self):
        """Verifica se a conta está vencida"""
        if self.dtPag or self.status == 'pago' or self.dtvenc is None:
            return False
        from django.utils import timezone
        return timezone.now().date() > self.dtvenc

    @property
    def dias_atraso(self):
        """Retorna o número de dias em atraso"""
        if self.is_vencida():
            from django.utils import timezone
            return (timezone.now().date() - self.dtvenc).days
        return 0

    def get_status_display(self):
        """Retorna o display do status"""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    class Meta:
        verbose_name = 'Conta a Pagar'
        verbose_name_plural = 'Contas a Pagar'
        ordering = ['-dtvenc', '-dtEmissao']