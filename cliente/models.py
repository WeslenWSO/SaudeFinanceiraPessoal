from django.db import models
from empresa.models import Empresa

# Create your models here.
class Cliente(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    conta_azul_id = models.CharField(
        max_length=36,
        blank=True,
        default='',
        db_index=True,
        verbose_name='ID Conta Azul',
    )
    razao = models.CharField(verbose_name='Razao', max_length=50)
    codigo_externo = models.CharField(
        verbose_name='Código externo',
        max_length=50,
        blank=True,
        default='',
        help_text='Usado na pasta ao salvar cópia do XML da NFSe (prestador): código-razão do tomador.',
    )
    cnpj = models.CharField(verbose_name='CNPJ', max_length=14)
    telefone = models.CharField(verbose_name='Telefone', max_length=11)
    descricao_extrato_bancario = models.CharField(
        verbose_name='Texto no extrato bancário',
        max_length=255,
        blank=True,
        default='',
        help_text='Trecho que aparece no histórico do extrato para este CNPJ/CPF. Conciliação automática quando CNPJ no extrato e nome curto não batem.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'conta_azul_id'],
                condition=models.Q(conta_azul_id__gt=''),
                name='cliente_conta_azul_unico',
            ),
        ]

    def __str__(self):
        return self.razao