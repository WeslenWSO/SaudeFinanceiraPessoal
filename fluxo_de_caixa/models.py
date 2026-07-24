from django.db import models
from empresa.models import Empresa

class CategoriaFluxoCaixa(models.Model):
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=[
        ('receita', 'Receita'),
        ('despesa', 'Despesa'),
        ('lucro_prejuizo', 'Lucro ou Prejuízo'),
        ('investimentos', 'Investimentos'),
        ('distribuicao_lucro', 'Distribuição de Lucro'),
        ('resultado_final', 'Resultado Final'),
    ])
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    def __str__(self):
        return self.nome

class EntradaFluxoCaixa(models.Model):
    categoria = models.ForeignKey(CategoriaFluxoCaixa, on_delete=models.CASCADE)
    ano = models.IntegerField()
    mes = models.IntegerField(choices=[(i, i) for i in range(1, 13)])
    valor = models.DecimalField(max_digits=15, decimal_places=2)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('categoria', 'ano', 'mes', 'empresa')

    def __str__(self):
        return f"{self.categoria.nome} - {self.ano}/{self.mes}"
