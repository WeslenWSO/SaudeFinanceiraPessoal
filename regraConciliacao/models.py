from django.db import models
from empresa.models import Empresa
from categoria.models import Categoria
from cobranca.models import Cobranca
from fornecedor.models import Fornecedor
from extrato.models import Banco, ContaBancaria

class RegraConciliacao(models.Model):
    TIPO_CONCILIACAO_CHOICES = [
        ('conciliacao', 'Conciliação'),
        ('transferencia', 'Transferência'),
    ]

    TIPO_LANCAMENTO_CHOICES = [
        ('contas_pagar', 'Contas a Pagar'),
        ('contas_receber', 'Contas a Receber'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, verbose_name='Categoria', null=True, blank=True)
    forma_pagamento = models.ForeignKey(Cobranca, on_delete=models.CASCADE, verbose_name='Forma de Pagamento', null=True, blank=True)
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, verbose_name='Fornecedor', null=True, blank=True)
    cliente = models.ForeignKey('cliente.Cliente', on_delete=models.CASCADE, verbose_name='Cliente', null=True, blank=True)
    conta_bancaria_destino = models.ForeignKey(ContaBancaria, on_delete=models.CASCADE, verbose_name='Conta Bancária Destino', null=True, blank=True)
    descricao = models.CharField(verbose_name='Descrição', max_length=255, default='')
    tipo_conciliacao = models.CharField(verbose_name='Tipo de Conciliação', max_length=20, choices=TIPO_CONCILIACAO_CHOICES, default='conciliacao')
    tipo_lancamento = models.CharField(verbose_name='Tipo de Lançamento', max_length=20, choices=TIPO_LANCAMENTO_CHOICES, default='contas_pagar')
    definicao_historico = models.CharField(verbose_name='Definição para Histórico', max_length=255)
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Regra de Conciliação'
        verbose_name_plural = 'Regras de Conciliação'
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.categoria} - {self.definicao_historico}"
