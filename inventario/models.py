from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from empresa.models import Empresa
from estoque.models import ProdutoEstoque


class Inventario(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='inventarios',
        verbose_name='Empresa',
    )
    descricao = models.CharField(max_length=200, verbose_name='Descrição')
    aberto = models.BooleanField(default=True, verbose_name='Aberto')
    rodada_atualiza_estoque = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Rodada que atualiza o estoque',
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text='0 = nenhuma; 1, 2 ou 3 = contagem usada para aplicar no estoque.',
    )
    estoque_aplicado_em = models.DateTimeField(null=True, blank=True)
    estoque_aplicado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventarios_estoque_aplicado',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventarios_criados',
        verbose_name='Criado por',
    )

    class Meta:
        verbose_name = 'Inventário'
        verbose_name_plural = 'Inventários'
        ordering = ['-criado_em']

    def __str__(self) -> str:
        return f'{self.descricao} ({self.empresa})'


class InventarioResponsavelContagem(models.Model):
    inventario = models.ForeignKey(
        Inventario,
        on_delete=models.CASCADE,
        related_name='responsaveis_contagem',
        verbose_name='Inventário',
    )
    rodada = models.PositiveSmallIntegerField(
        verbose_name='Rodada',
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='inventario_contagens_atribuidas',
        verbose_name='Usuário',
    )

    class Meta:
        verbose_name = 'Responsável pela contagem'
        verbose_name_plural = 'Responsáveis pelas contagens'
        constraints = [
            models.UniqueConstraint(
                fields=('inventario', 'rodada', 'usuario'),
                name='inventario_responsavel_unico_rodada_usuario',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.inventario_id} — {self.rodada}ª — {self.usuario}'


class InventarioItem(models.Model):
    inventario = models.ForeignKey(
        Inventario,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='Inventário',
    )
    produto = models.ForeignKey(
        ProdutoEstoque,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linhas_inventario',
        verbose_name='Produto',
    )
    codigo_produto = models.CharField(max_length=50, verbose_name='Código')
    descricao_produto = models.CharField(max_length=300, verbose_name='Produto')
    quantidade_estoque = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name='Qtd. estoque (sistema)',
    )
    quantidade_estoque_contabil = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name='Est. contábil (sistema)',
    )

    contagem_1 = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='1ª contagem',
    )
    contagem_1_em = models.DateTimeField(null=True, blank=True)
    contagem_1_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventario_contagens_1',
    )

    contagem_2 = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='2ª contagem',
    )
    contagem_2_em = models.DateTimeField(null=True, blank=True)
    contagem_2_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventario_contagens_2',
    )

    contagem_3 = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='3ª contagem',
    )
    contagem_3_em = models.DateTimeField(null=True, blank=True)
    contagem_3_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventario_contagens_3',
    )

    class Meta:
        verbose_name = 'Item do inventário'
        verbose_name_plural = 'Itens do inventário'
        ordering = ['codigo_produto', 'descricao_produto']
        constraints = [
            models.UniqueConstraint(
                fields=('inventario', 'codigo_produto'),
                name='inventario_item_codigo_unico',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.codigo_produto} — {self.descricao_produto}'

    def valor_contagem(self, rodada: int) -> Decimal | None:
        return getattr(self, f'contagem_{rodada}', None)

    def diferenca_contagem(self, rodada: int) -> Decimal | None:
        valor = self.valor_contagem(rodada)
        if valor is None:
            return None
        return valor - self.quantidade_estoque

    def contagem_bate_estoque(self, rodada: int) -> bool:
        diff = self.diferenca_contagem(rodada)
        return diff is not None and diff == Decimal('0')

    def feedback_contagens(self) -> list[str]:
        msgs: list[str] = []
        for rodada in (1, 2, 3):
            if self.valor_contagem(rodada) is None:
                continue
            if self.contagem_bate_estoque(rodada):
                msgs.append(f'{rodada}ª contagem confere com o estoque')
            else:
                diff = self.diferenca_contagem(rodada)
                msgs.append(f'{rodada}ª contagem diverge do estoque ({diff:+.3f})')
        return msgs

    @property
    def diff_1(self):
        return self.diferenca_contagem(1)

    @property
    def diff_2(self):
        return self.diferenca_contagem(2)

    @property
    def diff_3(self):
        return self.diferenca_contagem(3)

    def quantidade_para_aplicar(self, rodada: int) -> Decimal | None:
        if rodada not in (1, 2, 3):
            return None
        return self.valor_contagem(rodada)


class EstoqueBackup(models.Model):
    inventario = models.ForeignKey(
        Inventario,
        on_delete=models.CASCADE,
        related_name='backups_estoque',
        verbose_name='Inventário',
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='backups_estoque',
    )
    descricao = models.CharField(max_length=200, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='backups_estoque_criados',
    )

    class Meta:
        verbose_name = 'Backup de estoque'
        verbose_name_plural = 'Backups de estoque'
        ordering = ['-criado_em']

    def __str__(self) -> str:
        return f'Backup {self.criado_em:%d/%m/%Y %H:%M} — {self.inventario_id}'


class EstoqueBackupLinha(models.Model):
    backup = models.ForeignKey(
        EstoqueBackup,
        on_delete=models.CASCADE,
        related_name='linhas',
    )
    produto = models.ForeignKey(
        ProdutoEstoque,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    codigo_produto = models.CharField(max_length=50)
    descricao = models.CharField(max_length=300)
    marca = models.CharField(max_length=120, blank=True, default='')
    quantidade_estoque = models.DecimalField(max_digits=14, decimal_places=3)
    quantidade_estoque_contabil = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    valor_ultima_compra = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    valor_custo_medio = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    valor_custo_contabil = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    class Meta:
        verbose_name = 'Linha do backup de estoque'
        verbose_name_plural = 'Linhas do backup de estoque'
        ordering = ['codigo_produto']
