from django.db import models
from empresa.models import Empresa

# Create your models here.
class Categoria(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    nome = models.CharField(verbose_name='Nome', max_length=100)
    grupo = models.CharField(verbose_name='Grupo', max_length=100, blank=True, null=True)
    classificacao = models.CharField(verbose_name='Classificacao', max_length=30)
    sintetico = models.CharField(verbose_name='sintetico', max_length=1,  default='A',
                             choices=(
                                         ('A', 'ANALITICO'),
                                         ('S', 'SINTETICO'),

                                     ),)

    tipo = models.CharField(verbose_name='Tipo', max_length=1, default='D',
                           choices=(
                                       ('R', 'RECEITA'),
                                       ('D', 'DESPESAS'),
                                       ('I', 'INVESTIMENTO'),
                                       ('L', 'DISTRIBUICAO DE LUCRO'),
                                   ),)
    
    
    
    def __str__(self):
        return f'{self.nome} {self.classificacao}'