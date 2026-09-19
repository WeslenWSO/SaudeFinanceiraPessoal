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
