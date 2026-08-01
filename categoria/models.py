from django.db import models
from empresa.models import Empresa

# Create your models here.
class Categoria(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    conta_azul_id = models.CharField(
        max_length=36,
        blank=True,
        default='',
        db_index=True,
        verbose_name='ID Conta Azul',
    )
    nome = models.CharField(verbose_name='Nome', max_length=100)
    grupo = models.CharField(
        verbose_name='Grupo',
        max_length=100,
        blank=True,
        null=True,
        help_text='Categoria pai no Conta Azul (campo "Aparecer dentro da categoria").',
    )
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
    bloquear_sync_conta_azul = models.BooleanField(
        default=False,
        verbose_name='Manter configuração local na sync Conta Azul',
        help_text=(
            'Marcado: a reimportação do Conta Azul não altera nome, tipo, grupo, '
            'classificação nem sintético desta categoria.'
        ),
    )
    def __str__(self):
        return f'{self.nome} {self.classificacao}'


class CentroCusto(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='centros_custo',
        verbose_name='Empresa',
    )
    conta_azul_id = models.CharField(max_length=36, blank=True, default='', db_index=True)
    nome = models.CharField(max_length=200, verbose_name='Nome')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    codigo = models.CharField(max_length=60, blank=True, default='')

    class Meta:
        verbose_name = 'Centro de custo'
        verbose_name_plural = 'Centros de custo'
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'conta_azul_id'],
                condition=models.Q(conta_azul_id__gt=''),
                name='centro_custo_conta_azul_unico',
            ),
        ]

    def __str__(self):
        return self.nome