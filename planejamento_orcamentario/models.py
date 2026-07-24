from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import models, transaction

from empresa.models import Empresa


def _add_months(d: date, months: int) -> date:
    """Avança N meses mantendo o dia (ajusta se o mês for mais curto)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


class ItemOrcamento(models.Model):
    """Item do planejamento orçamentário (receita, despesa ou imposto)."""

    TIPO_RECEITA = 'receita'
    TIPO_FIXA = 'fixa'
    TIPO_SEMI_FIXA = 'semi_fixa'
    TIPO_VARIAVEL = 'variavel'
    TIPO_IMPOSTO = 'imposto'

    TIPO_CHOICES = [
        (TIPO_RECEITA, 'Receitas'),
        (TIPO_FIXA, 'Despesas fixas'),
        (TIPO_SEMI_FIXA, 'Despesas semi-fixas'),
        (TIPO_VARIAVEL, 'Despesas variáveis'),
        (TIPO_IMPOSTO, 'Impostos'),
    ]

    FORMA_FIXO = 'fixo'
    FORMA_PERCENTUAL = 'percentual'
    FORMA_CHOICES = [
        (FORMA_FIXO, 'Valor fixo / previsto'),
        (FORMA_PERCENTUAL, '% sobre receitas'),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='itens_orcamento',
        verbose_name='Empresa',
    )
    categoria = models.ForeignKey(
        'categoria.Categoria',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens_orcamento',
        verbose_name='Categoria',
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name='Tipo',
        db_index=True,
    )
    nome = models.CharField(max_length=200, verbose_name='Nome')
    observacao = models.TextField(blank=True, default='', verbose_name='Observação')
    forma_calculo = models.CharField(
        max_length=20,
        choices=FORMA_CHOICES,
        default=FORMA_FIXO,
        verbose_name='Forma de cálculo',
    )
    valor_mensal = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Valor mensal previsto',
        help_text='Usado quando a forma é valor fixo/previsto.',
    )
    valor_min = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Valor mínimo',
        help_text='Faixa típica (semi-fixas).',
    )
    valor_max = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Valor máximo',
        help_text='Faixa típica (semi-fixas).',
    )
    aliquota_pct = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('0'),
        verbose_name='Alíquota (%)',
        help_text='Para impostos ou variáveis sobre faturamento/receitas.',
    )
    data_inicio = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data do mês inicial',
        help_text='Data do primeiro lançamento. Os demais repetem no mesmo dia nos meses seguintes.',
    )
    qtd_meses = models.PositiveIntegerField(
        default=1,
        verbose_name='Quantidade de meses',
        help_text='Quantos meses o lançamento deve se repetir (incluindo o mês inicial).',
    )
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    ordem = models.PositiveIntegerField(default=0, verbose_name='Ordem')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Item orçamentário'
        verbose_name_plural = 'Itens orçamentários'
        ordering = ['tipo', 'ordem', 'nome']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.nome}'

    @classmethod
    def tipo_meta(cls, tipo):
        """Rótulo, ícone e descrição de ajuda por tipo."""
        meta = {
            cls.TIPO_RECEITA: {
                'titulo': 'Receitas',
                'icone': 'fa-arrow-up',
                'cor': 'success',
                'ajuda': 'Entradas previstas (faturamento, repasses, etc.).',
            },
            cls.TIPO_FIXA: {
                'titulo': 'Despesas fixas',
                'icone': 'fa-lock',
                'cor': 'secondary',
                'ajuda': 'Todo mês com valor estável (aluguel, salários, condomínio).',
            },
            cls.TIPO_SEMI_FIXA: {
                'titulo': 'Despesas semi-fixas',
                'icone': 'fa-bolt',
                'cor': 'warning',
                'ajuda': 'Ocorrem todo mês, mas o valor oscila (energia, água, internet).',
            },
            cls.TIPO_VARIAVEL: {
                'titulo': 'Despesas variáveis',
                'icone': 'fa-chart-line',
                'cor': 'info',
                'ajuda': 'Variam com produção ou faturamento (insumos, comissões).',
            },
            cls.TIPO_IMPOSTO: {
                'titulo': 'Impostos',
                'icone': 'fa-percent',
                'cor': 'danger',
                'ajuda': 'Obrigações tributárias (ISS, PIS, COFINS, CSLL, IRPJ, DAS…).',
            },
        }
        return meta.get(tipo, {'titulo': tipo, 'icone': 'fa-tag', 'cor': 'primary', 'ajuda': ''})

    def valor_estimado(self, total_receitas=None):
        """Valor mensal estimado (para % usa total de receitas quando informado)."""
        if self.forma_calculo == self.FORMA_PERCENTUAL and (self.aliquota_pct or 0) > 0:
            base = total_receitas if total_receitas is not None else Decimal('0')
            return (base * (self.aliquota_pct or Decimal('0')) / Decimal('100')).quantize(
                Decimal('0.01')
            )
        if self.tipo == self.TIPO_SEMI_FIXA and (self.valor_mensal or 0) <= 0:
            vmin = self.valor_min or Decimal('0')
            vmax = self.valor_max or Decimal('0')
            if vmin > 0 or vmax > 0:
                return ((vmin + vmax) / Decimal('2')).quantize(Decimal('0.01'))
        return (self.valor_mensal or Decimal('0')).quantize(Decimal('0.01'))

    def periodo_rotulo(self):
        if not self.data_inicio:
            return '—'
        n = max(1, int(self.qtd_meses or 1))
        if n == 1:
            return self.data_inicio.strftime('%d/%m/%Y')
        fim = _add_months(self.data_inicio, n - 1)
        return f'{self.data_inicio.strftime("%d/%m/%Y")} → {fim.strftime("%d/%m/%Y")} ({n} meses)'

    @staticmethod
    def total_receitas_no_mes(empresa, ano, mes):
        """Soma dos lançamentos de receita ativos no mês/ano informado."""
        from django.db.models import Sum

        return (
            LancamentoOrcamento.objects.filter(
                empresa=empresa,
                item__tipo=ItemOrcamento.TIPO_RECEITA,
                item__ativo=True,
                data_lancamento__year=ano,
                data_lancamento__month=mes,
            ).aggregate(t=Sum('valor'))['t']
            or Decimal('0')
        )

    @transaction.atomic
    def gerar_lancamentos(self, total_receitas=None):
        """
        Gera/regenera os lançamentos mensais:
        1º na data_inicio; demais no mesmo dia dos meses seguintes.

        Se forma = % sobre receitas, cada mês usa a soma das receitas
        lançadas naquele mês (não um valor único para todos).
        """
        self.lancamentos.all().delete()
        if not self.data_inicio:
            return 0
        n = max(1, int(self.qtd_meses or 1))
        usa_pct = (
            self.forma_calculo == self.FORMA_PERCENTUAL
            and (self.aliquota_pct or 0) > 0
        )
        valor_fixo = None if usa_pct else self.valor_estimado(total_receitas)
        criar = []
        for i in range(n):
            data_lanc = _add_months(self.data_inicio, i)
            if usa_pct:
                base = self.total_receitas_no_mes(
                    self.empresa, data_lanc.year, data_lanc.month
                )
                # Fallback: se ainda não há lançamento de receita no mês,
                # usa o valor mensal cadastrado nos itens de receita.
                if base <= 0 and total_receitas is not None:
                    base = total_receitas
                valor = self.valor_estimado(base)
            else:
                valor = valor_fixo
            criar.append(
                LancamentoOrcamento(
                    item=self,
                    empresa=self.empresa,
                    data_lancamento=data_lanc,
                    valor=valor,
                    sequencia=i + 1,
                )
            )
        LancamentoOrcamento.objects.bulk_create(criar)
        return len(criar)

    @classmethod
    def regenerar_percentuais(cls, empresa):
        """Recalcula impostos/variáveis com % após alterar receitas."""
        qs = cls.objects.filter(
            empresa=empresa,
            ativo=True,
            forma_calculo=cls.FORMA_PERCENTUAL,
        )
        total = 0
        for it in qs:
            total += it.gerar_lancamentos()
        return total


class LancamentoOrcamento(models.Model):
    """Lançamento mensal gerado a partir do item (repetição)."""

    item = models.ForeignKey(
        ItemOrcamento,
        on_delete=models.CASCADE,
        related_name='lancamentos',
        verbose_name='Item',
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='lancamentos_orcamento',
        verbose_name='Empresa',
    )
    data_lancamento = models.DateField(verbose_name='Data do lançamento', db_index=True)
    valor = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Valor',
    )
    sequencia = models.PositiveIntegerField(default=1, verbose_name='Sequência')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lançamento orçamentário'
        verbose_name_plural = 'Lançamentos orçamentários'
        ordering = ['data_lancamento', 'sequencia']
        indexes = [
            models.Index(fields=['empresa', 'data_lancamento']),
        ]

    def __str__(self):
        return f'{self.item.nome} — {self.data_lancamento} — R$ {self.valor}'
