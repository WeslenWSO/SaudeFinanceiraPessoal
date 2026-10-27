from django.conf import settings
from django.db import models

from empresa.models import Empresa
from estoque.setores import SetorEstoque


class NaturezaEstoque(models.TextChoices):
    CONSUMIVEL = 'consumivel', 'Consumível (farmácia / materiais)'
    IMOBILIZADO = 'imobilizado', 'Imobilizado'


class ProdutoEstoque(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='produtos_estoque',
        verbose_name='Empresa',
    )
    natureza = models.CharField(
        max_length=16,
        choices=NaturezaEstoque.choices,
        default=NaturezaEstoque.CONSUMIVEL,
        verbose_name='Natureza',
        help_text='Consumível: farmácia e requisições. Imobilizado: patrimônio / bens.',
    )
    setor_localizacao = models.CharField(
        max_length=32,
        choices=SetorEstoque.choices,
        blank=True,
        default='',
        verbose_name='Setor (localização)',
        help_text='Para imobilizado: setor clínico onde o bem está.',
    )
    codigo_produto = models.CharField(max_length=50, verbose_name='Código do produto')
    descricao = models.CharField(max_length=300, verbose_name='Descrição do produto')
    marca = models.CharField(max_length=120, blank=True, default='', verbose_name='Marca')
    fornecedor = models.ForeignKey(
        'fornecedor.Fornecedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='produtos_estoque',
        verbose_name='Fornecedor',
        help_text='Fornecedor habitual (pode vir da última NF de compra).',
    )
    unidade_master = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Unidade master',
        help_text='Ex.: PCT, CX (embalagem maior)',
    )
    quantidade_por_master = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Unidades por master',
        help_text='Quantas unidades de consumo vêm em 1 unidade master (ex.: 1 PCT = 4 UN → informe 4).',
    )
    unidade = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Unidade',
        help_text='Unidade de consumo (ex.: UN, ML)',
    )
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
    estoque_minimo = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Estoque mínimo',
        help_text='Alerta quando a quantidade na farmácia ficar abaixo deste valor.',
    )
    dias_entrega_fornecedor = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Dias para entrega',
        help_text='Prazo médio (dias) que o fornecedor demora para entregar.',
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

    @property
    def rotulo_unidade_master(self) -> str:
        """Ex.: «1 PCT = 4 UN» ou só «PCT»."""
        master = (self.unidade_master or '').strip()
        if not master:
            return ''
        qtd = self.quantidade_por_master or 0
        un = (self.unidade or '').strip()
        if qtd > 0 and un:
            q_fmt = f'{qtd:f}'.rstrip('0').rstrip('.')
            return f'1 {master} = {q_fmt} {un}'
        return master

    @property
    def fornecedor_rotulo(self) -> str:
        if not self.fornecedor_id:
            return ''
        f = self.fornecedor
        return (f.nome_fantasia or f.razao or '').strip()

    @property
    def abaixo_estoque_minimo(self) -> bool:
        minimo = self.estoque_minimo or 0
        if minimo <= 0:
            return False
        return (self.quantidade_estoque or 0) < minimo


class SaldoEstoqueSetor(models.Model):
    produto = models.ForeignKey(
        ProdutoEstoque,
        on_delete=models.CASCADE,
        related_name='saldos_setor',
    )
    setor = models.CharField(max_length=32, choices=SetorEstoque.choices)
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    class Meta:
        verbose_name = 'Saldo por setor'
        verbose_name_plural = 'Saldos por setor'
        constraints = [
            models.UniqueConstraint(
                fields=('produto', 'setor'),
                name='saldo_estoque_setor_unico',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.produto.codigo_produto} @ {self.get_setor_display()}: {self.quantidade}'


class SetorEstoqueResponsavel(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='responsaveis_estoque')
    setor = models.CharField(max_length=32, choices=SetorEstoque.choices)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='setores_estoque_responsavel',
    )

    class Meta:
        verbose_name = 'Responsável de setor (estoque)'
        constraints = [
            models.UniqueConstraint(
                fields=('empresa', 'setor', 'usuario'),
                name='setor_estoque_resp_unico',
            ),
        ]


class ProdutoCodigoNotaDePara(models.Model):
    """Vincula código do item na NF de comércio ao código cadastrado no estoque."""

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='de_para_codigo_nota',
        verbose_name='Empresa',
    )
    codigo_nota = models.CharField(
        max_length=50,
        verbose_name='Código na nota',
        help_text='Código do produto como veio no XML/NF do fornecedor.',
    )
    fornecedor = models.ForeignKey(
        'fornecedor.Fornecedor',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='de_para_codigo_nota',
        verbose_name='Fornecedor',
        help_text='Vazio = vale para qualquer fornecedor com este código na NF.',
    )
    produto = models.ForeignKey(
        ProdutoEstoque,
        on_delete=models.CASCADE,
        related_name='de_para_codigos_nota',
        verbose_name='Produto no estoque',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'De-para código NF → estoque'
        verbose_name_plural = 'De-para códigos NF → estoque'
        constraints = [
            models.UniqueConstraint(
                fields=('empresa', 'codigo_nota'),
                condition=models.Q(fornecedor__isnull=True),
                name='depara_nota_global_unico',
            ),
            models.UniqueConstraint(
                fields=('empresa', 'codigo_nota', 'fornecedor'),
                condition=models.Q(fornecedor__isnull=False),
                name='depara_nota_fornecedor_unico',
            ),
        ]

    def __str__(self) -> str:
        alvo = self.produto.codigo_produto if self.produto_id else '—'
        return f'NF {self.codigo_nota} → {alvo}'


class EntradaEstoqueNota(models.Model):
    nota_item = models.OneToOneField(
        'notafiscalentrada.NotaFiscalEntradaItem',
        on_delete=models.PROTECT,
        related_name='entrada_estoque',
    )
    produto = models.ForeignKey(
        ProdutoEstoque,
        on_delete=models.PROTECT,
        related_name='entradas_nota',
    )
    quantidade = models.DecimalField(max_digits=14, decimal_places=3)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=4)
    marca = models.CharField(max_length=120, blank=True, default='')
    unidade_master = models.CharField(max_length=20, blank=True, default='')
    quantidade_por_master = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    data_validade = models.DateField(null=True, blank=True)
    movimento = models.OneToOneField(
        'MovimentoEstoque',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entrada_vinculada',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Entrada de estoque (NF)'
        verbose_name_plural = 'Entradas de estoque (NF)'


class MovimentoEstoque(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA_NF = 'entrada_nf', 'Entrada NF'
        TRANSFERENCIA = 'transferencia', 'Transferência'
        BAIXA = 'baixa', 'Baixa / consumo'
        AJUSTE = 'ajuste', 'Ajuste inventário'

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='movimentos_estoque')
    produto = models.ForeignKey(ProdutoEstoque, on_delete=models.PROTECT, related_name='movimentos')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    setor_origem = models.CharField(max_length=32, blank=True, default='')
    setor_destino = models.CharField(max_length=32, blank=True, default='')
    quantidade = models.DecimalField(max_digits=14, decimal_places=3)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    valor_custo_medio_apos = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    nota_item = models.ForeignKey(
        'notafiscalentrada.NotaFiscalEntradaItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimentos_estoque',
    )
    requisicao = models.ForeignKey(
        'RequisicaoEstoque',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimentos',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    observacao = models.CharField(max_length=500, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Movimento de estoque'
        verbose_name_plural = 'Movimentos de estoque'


class RequisicaoEstoque(models.Model):
    class Tipo(models.TextChoices):
        TRANSFERENCIA = 'transferencia', 'Transferência (Farmácia → setor)'
        BAIXA_FARMACIA = 'baixa_farmacia', 'Baixa direta (Farmácia)'
        BAIXA_SETOR = 'baixa_setor', 'Baixa no setor'

    class Status(models.TextChoices):
        RASCUNHO = 'rascunho', 'Rascunho'
        CONCLUIDA = 'concluida', 'Concluída'
        CANCELADA = 'cancelada', 'Cancelada'

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='requisicoes_estoque')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    setor_origem = models.CharField(
        max_length=32,
        choices=SetorEstoque.choices,
        default=SetorEstoque.FARMACIA,
    )
    setor_destino = models.CharField(
        max_length=32,
        choices=SetorEstoque.choices,
        blank=True,
        default='',
    )
    setor_consumo = models.CharField(
        max_length=32,
        choices=SetorEstoque.choices,
        blank=True,
        default='',
        verbose_name='Setor de uso / consumo',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RASCUNHO)
    observacao = models.CharField(max_length=500, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='requisicoes_estoque_criadas',
    )
    concluida_em = models.DateTimeField(null=True, blank=True)
    concluida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisicoes_estoque_concluidas',
    )

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Requisição de estoque'
        verbose_name_plural = 'Requisições de estoque'


class RequisicaoEstoqueItem(models.Model):
    requisicao = models.ForeignKey(RequisicaoEstoque, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(ProdutoEstoque, on_delete=models.PROTECT, related_name='itens_requisicao')
    quantidade = models.DecimalField(max_digits=14, decimal_places=3)
    quantidade_atendida = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    class Meta:
        verbose_name = 'Item da requisição'
        verbose_name_plural = 'Itens da requisição'
