from django.db import models
from empresa.models import Empresa

class RelatorioRecebiveisMaquinaCartao(models.Model):
    MAQUINHA_CHOICES = [
        ('SIPAG', 'SIPAG'),
        ('CIELO', 'CIELO'),
        ('INFINTY', 'INFINTY'),
        ('INFINITEPAY', 'Infinite Pay'),
        ('GETNET', 'GETNET'),
        ('SAFRAPAY', 'SAFRAPAY'),
        ('SUMUP', 'SUMUP'),
        ('PAGBANK', 'PAGBANK'),
        ('STONE', 'STONE'),
        ('MERCADOPAGO', 'MERCADOPAGO'),
        ('OUTROS', 'OUTROS'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    data_pagamento = models.DateField(verbose_name='Data de Pagamento', null=True, blank=True)
    forma_pagamento = models.CharField(verbose_name='Forma de Pagamento', max_length=50, blank=True, null=True)
    bandeira = models.CharField(verbose_name='Bandeira', max_length=50, blank=True, null=True)
    valor_bruto = models.DecimalField(verbose_name='Valor Bruto', max_digits=10, decimal_places=2, default=0)
    taxa_maquinha = models.DecimalField(verbose_name='Taxa de Maquinha', max_digits=5, decimal_places=2, default=0)
    valor_liquido = models.DecimalField(verbose_name='Valor Líquido', max_digits=10, decimal_places=2, default=0)
    maquinha = models.CharField(verbose_name='Maquinha', max_length=50, choices=MAQUINHA_CHOICES, blank=True, null=True)
    numero_autorizacao = models.CharField(verbose_name='N. Autorizacao', max_length=50, blank=True, null=True)
    data_venda = models.CharField(verbose_name='Data da Venda', max_length=50, blank=True, null=True)
    nsu_doc = models.CharField(verbose_name='NSU/DOC', max_length=50, blank=True, null=True)
    parcelas = models.IntegerField(verbose_name='Parcelas', default=1)
    total_parcelas = models.IntegerField(verbose_name='Total Parcelas', default=1)
    parcela_texto = models.CharField(
        verbose_name='Parcela',
        max_length=40,
        blank=True,
        null=True,
        help_text='Texto como no relatório (ex.: 1 / 2). Opcional; parcelas e total_parcelas podem ser derivados.',
    )
    conciliado = models.BooleanField(verbose_name='Conciliado', default=False)
    identificacao_extrato = models.CharField(verbose_name='Identificação Extrato', max_length=100, blank=True, null=True)
    nota_fiscal = models.CharField(verbose_name='Nota Fiscal', max_length=50, blank=True, null=True)
    conta_a_receber = models.ForeignKey('contasareceber.ContaAReceber', verbose_name='Conta a Receber', on_delete=models.SET_NULL, null=True, blank=True)
    razao = models.CharField(verbose_name='Razão', max_length=200, blank=True, null=True)
    conta_bancaria = models.CharField(verbose_name='Conta Bancária', max_length=500, blank=True, null=True)

    def data_venda_como_date(self):
        """Converte data_venda (CharField) em date, se possível."""
        from datetime import datetime, date as date_cls

        raw = (self.data_venda or '').strip()
        if not raw:
            return None
        if isinstance(self.data_venda, date_cls) and not isinstance(self.data_venda, datetime):
            return self.data_venda
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except (ValueError, TypeError):
                continue
        return None

    @property
    def data_venda_display(self):
        d = self.data_venda_como_date()
        if d:
            return d.strftime('%d/%m/%Y')
        return (self.data_venda or '').strip() or '-'

    @property
    def data_venda_iso(self):
        """YYYY-MM-DD para filtro de emissão em Contas a Receber."""
        d = self.data_venda_como_date()
        return d.strftime('%Y-%m-%d') if d else ''

    @property
    def taxa_perc(self):
        if self.valor_bruto != 0:
            return round((self.taxa_maquinha / self.valor_bruto) * 100, 2)
        return 0

    class Meta:
        verbose_name = 'Relatório de Recebíveis Máquina de Cartão'
        verbose_name_plural = 'Relatórios de Recebíveis Máquina de Cartão'
        ordering = ['-data_pagamento']

    def __str__(self):
        empresa_nome = self.empresa.razao if self.empresa else "Sem Empresa"
        return f"Relatório {self.id} - {empresa_nome} - R$ {self.valor_liquido}"
