from django.db import models

from empresa.models import Empresa


class ProdutoEstoque(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='produtos_estoque',
        verbose_name='Empresa',
    )
    codigo_produto = models.CharField(max_length=50, verbose_name='Código do produto')
    descricao = models.CharField(max_length=300, verbose_name='Descrição do produto')
    marca = models.CharField(max_length=120, blank=True, default='', verbose_name='Marca')
    quantidade_estoque = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Quantidade em estoque',
    )
    quantidade_estoque_contabil = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Estoque contábil',
    )
    valor_ultima_compra = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name='Valor da última compra',
    )
    valor_custo_medio = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name='Valor custo médio',
    )
    valor_custo_contabil = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name='Valor custo contábil',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Produto (estoque)'
        verbose_name_plural = 'Produtos (estoque)'
        ordering = ['codigo_produto', 'descricao']
        constraints = [
            models.UniqueConstraint(
                fields=('empresa', 'codigo_produto'),
                name='produto_estoque_codigo_unico_empresa',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.codigo_produto} — {self.descricao}'
