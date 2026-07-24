from django.db import models
from empresa.models import Empresa

# Create your models here.




class RegraImposto(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Empresa',
        related_name='regras_imposto'
    )
    DescricaoRegraImposto = models.CharField(verbose_name='Regra', max_length=30)
    aliquota_pis = models.DecimalField(verbose_name='Alíquota PIS (%)', max_digits=5, decimal_places=2, default=0)
    aliquota_cofins = models.DecimalField(verbose_name='Alíquota COFINS (%)', max_digits=5, decimal_places=2, default=0)
    aliquota_csll = models.DecimalField(verbose_name='Alíquota CSLL (%)', max_digits=5, decimal_places=2, default=0)
    aliquota_irpj = models.DecimalField(verbose_name='Alíquota IRPJ (%)', max_digits=5, decimal_places=2, default=0)
    aliquota_iss_apuracao = models.DecimalField(verbose_name='Alíquota ISS Apuração (%)', max_digits=5, decimal_places=2, default=0)
    percentual_calculo = models.DecimalField(verbose_name='Percentual de Cálculo (%)', max_digits=5, decimal_places=2, default=100)
    ha_retencao = models.BooleanField(verbose_name='Há Retenção', default=False)


    def __str__(self):
        return self.DescricaoRegraImposto