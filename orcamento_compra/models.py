from decimal import Decimal

from django.conf import settings
from django.db import models

from empresa.models import Empresa
from estoque.models import ProdutoEstoque
from fornecedor.models import Fornecedor


class OrcamentoCompra(models.Model):
    STATUS_RASCUNHO = 'rascunho'
    STATUS_COTACAO = 'cotacao'
    STATUS_CONCLUIDO = 'concluido'
    STATUS_CHOICES = [
        (STATUS_RASCUNHO, 'Rascunho'),
        (STATUS_COTACAO, 'Em cotação'),
        (STATUS_CONCLUIDO, 'Concluído'),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='orcamentos_compra',
        verbose_name='Empresa',
    )
    titulo = models.CharField(max_length=200, verbose_name='Título')
    observacao = models.TextField(blank=True, default='', verbose_name='Observação')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RASCUNHO,
        verbose_name='Status',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orcamentos_compra_criados',
        verbose_name='Criado por',
    )

    class Meta:
        verbose_name = 'Orçamento de compra'
        verbose_name_plural = 'Orçamentos de compra'
        ordering = ['-atualizado_em', '-id']

    def __str__(self) -> str:
        return self.titulo


class OrcamentoCompraItem(models.Model):
    orcamento = models.ForeignKey(
        OrcamentoCompra,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='Orçamento',
    )
    produto = models.ForeignKey(
        ProdutoEstoque,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orcamentos_compra_itens',
        verbose_name='Produto (estoque)',
    )
    descricao = models.CharField(max_length=300, verbose_name='Produto / descrição')
    unidade = models.CharField(max_length=20, blank=True, default='UN', verbose_name='Unidade')
    quantidade = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('1'),
        verbose_name='Quantidade',
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name='Ordem')

    class Meta:
        verbose_name = 'Item do orçamento'
        verbose_name_plural = 'Itens do orçamento'
        ordering = ['ordem', 'id']

    def __str__(self) -> str:
        return f'{self.descricao} ({self.quantidade})'


class OrcamentoCompraFornecedor(models.Model):
    orcamento = models.ForeignKey(
        OrcamentoCompra,
        on_delete=models.CASCADE,
        related_name='fornecedores',
        verbose_name='Orçamento',
    )
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orcamentos_compra_colunas',
        verbose_name='Fornecedor',
    )
    nome_exibicao = models.CharField(
        max_length=200,
        verbose_name='Nome na tabela',
        help_text='Rótulo da coluna (ex.: razão social ou apelido).',
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name='Ordem')
    pdf_orcamento = models.FileField(
        upload_to='orcamento_compra/pdf/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='PDF do fornecedor',
    )
    pdf_texto = models.TextField(blank=True, default='', verbose_name='Texto extraído do PDF')
    observacao = models.TextField(blank=True, default='', verbose_name='Observação')

    class Meta:
        verbose_name = 'Fornecedor (coluna)'
        verbose_name_plural = 'Fornecedores (colunas)'
        ordering = ['ordem', 'id']

    def __str__(self) -> str:
        return self.nome_exibicao


class OrcamentoCompraPreco(models.Model):
    item = models.ForeignKey(
        OrcamentoCompraItem,
        on_delete=models.CASCADE,
        related_name='precos',
        verbose_name='Item',
    )
    coluna_fornecedor = models.ForeignKey(
        OrcamentoCompraFornecedor,
        on_delete=models.CASCADE,
        related_name='precos',
        verbose_name='Fornecedor',
    )
    preco_unitario = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Preço unitário',
    )
    preco_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Preço total',
        help_text='Opcional; se vazio, usa quantidade × unitário.',
    )
    observacao = models.CharField(max_length=255, blank=True, default='', verbose_name='Obs.')

    class Meta:
        verbose_name = 'Preço cotado'
        verbose_name_plural = 'Preços cotados'
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'coluna_fornecedor'],
                name='orcamento_preco_item_fornecedor_unico',
            ),
        ]

    def total_calculado(self) -> Decimal | None:
        if self.preco_total is not None:
            return self.preco_total
        if self.preco_unitario is not None and self.item_id:
            return (self.preco_unitario * self.item.quantidade).quantize(Decimal('0.01'))
        return None


class OrcamentoCompraResultadoVencedor(models.Model):
    """Pedido consolidado para um fornecedor após comparar preços (itens que venceu)."""

    orcamento = models.ForeignKey(
        OrcamentoCompra,
        on_delete=models.CASCADE,
        related_name='resultados_vencedores',
        verbose_name='Orçamento',
    )
    coluna_fornecedor = models.ForeignKey(
        OrcamentoCompraFornecedor,
        on_delete=models.CASCADE,
        related_name='resultados_vencedores',
        verbose_name='Fornecedor',
    )
    gerado_em = models.DateTimeField(auto_now_add=True)
    total_geral = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Total',
    )

    class Meta:
        verbose_name = 'Orçamento vencedor (fornecedor)'
        verbose_name_plural = 'Orçamentos vencedores (fornecedor)'
        constraints = [
            models.UniqueConstraint(
                fields=['orcamento', 'coluna_fornecedor'],
                name='orcamento_vencedor_unico_por_coluna',
            ),
        ]
        ordering = ['coluna_fornecedor__ordem', 'id']

    def __str__(self) -> str:
        return f'{self.coluna_fornecedor.nome_exibicao} — {self.orcamento.titulo}'


class OrcamentoCompraResultadoVencedorItem(models.Model):
    resultado = models.ForeignKey(
        OrcamentoCompraResultadoVencedor,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='Resultado',
    )
    item = models.ForeignKey(
        OrcamentoCompraItem,
        on_delete=models.CASCADE,
        related_name='vitorias_resultado',
        verbose_name='Item original',
    )
    descricao = models.CharField(max_length=300, verbose_name='Produto')
    unidade = models.CharField(max_length=20, default='UN')
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('1'))
    preco_unitario = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    preco_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Item do orçamento vencedor'
        verbose_name_plural = 'Itens do orçamento vencedor'
        ordering = ['ordem', 'id']
