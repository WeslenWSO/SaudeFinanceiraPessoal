from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Sum

from empresa.models import Empresa


INDICADORES_PADRAO: dict[str, list[str]] = {
    'MUSCULACAO': [
        'NPS GERAL',
        'NPS MUSCULAÇÃO',
        'NPS POR HORA',
        'MONTAGEM DE TREINO',
        'CHURN',
    ],
    'ATENDENTE': [
        'NPS geral',
        'NPS recepção',
        'NPS por horario',
        'Conversão',
        'Vendas',
        'Redução inadimplentes',
    ],
}

PREMIACAO_PROPORCAO_PADRAO: dict[str, tuple[str, Decimal, Decimal]] = {
    'NPS GERAL': ('MUSCULACAO', Decimal('30.00'), Decimal('15.00')),
    'NPS MUSCULAÇÃO': ('MUSCULACAO', Decimal('80.00'), Decimal('40.00')),
    'NPS POR HORA': ('MUSCULACAO', Decimal('30.00'), Decimal('15.00')),
    'MONTAGEM DE TREINO': ('MUSCULACAO', Decimal('30.00'), Decimal('15.00')),
    'CHURN': ('MUSCULACAO', Decimal('30.00'), Decimal('15.00')),
}


class Indicador(models.Model):
    AREA_MUSCULACAO = 'MUSCULACAO'
    AREA_ATENDENTE = 'ATENDENTE'
    AREA_CHOICES = [
        (AREA_MUSCULACAO, 'Musculação'),
        (AREA_ATENDENTE, 'Atendente'),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='indicadores',
        verbose_name='Empresa',
    )
    area = models.CharField(
        verbose_name='Área',
        max_length=20,
        choices=AREA_CHOICES,
    )
    nome = models.CharField(verbose_name='Indicador', max_length=120)
    ordem = models.PositiveSmallIntegerField(verbose_name='Ordem', default=0)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    premiacao = models.DecimalField(
        verbose_name='Premiação (R$)',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    proporcao = models.DecimalField(
        verbose_name='Proporção (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
    )

    class Meta:
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'
        ordering = ['area', 'ordem', 'nome']
        unique_together = [['empresa', 'area', 'nome']]

    def __str__(self):
        return f'{self.get_area_display()} — {self.nome}'

    @property
    def eh_churn(self) -> bool:
        return self.nome.strip().upper() == 'CHURN'


class PeriodoAcademia(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='periodos_academia',
        verbose_name='Empresa',
    )
    ano = models.PositiveIntegerField(verbose_name='Ano')
    mes = models.PositiveIntegerField(verbose_name='Mês')
    data_referencia = models.DateField(verbose_name='Data dos dados', null=True, blank=True)
    qt_ativos = models.PositiveIntegerField(verbose_name='Qt. ativos', default=0)
    qt_cancelados = models.PositiveIntegerField(verbose_name='Qt. cancelados', default=0)
    churn_pct = models.DecimalField(
        verbose_name='Churn (%)',
        max_digits=7,
        decimal_places=4,
        default=Decimal('0.0000'),
        editable=False,
    )

    class Meta:
        verbose_name = 'Período academia'
        verbose_name_plural = 'Períodos academia'
        ordering = ['-ano', '-mes']
        unique_together = [['empresa', 'ano', 'mes']]

    def __str__(self):
        return f'{self.mes:02d}/{self.ano}'

    def recalcular_churn(self) -> None:
        if self.qt_ativos:
            pct = (Decimal(self.qt_cancelados) / Decimal(self.qt_ativos)) * Decimal('100')
            self.churn_pct = pct.quantize(Decimal('0.0001'))
        else:
            self.churn_pct = Decimal('0.0000')

    def save(self, *args, **kwargs):
        self.recalcular_churn()
        super().save(*args, **kwargs)
        recalcular_lancamentos_mes(self)


def obter_periodo_mm_aaaa(empresa_id, ano: int, mes: int) -> 'PeriodoAcademia | None':
    if not empresa_id:
        return None
    return PeriodoAcademia.objects.filter(empresa_id=empresa_id, ano=ano, mes=mes).first()


def obter_periodo_por_data(empresa_id, data: date) -> 'PeriodoAcademia | None':
    if not data:
        return None
    return obter_periodo_mm_aaaa(empresa_id, data.year, data.month)


class ItemPeriodoAcademia(models.Model):
    periodo = models.ForeignKey(
        PeriodoAcademia,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='Período',
    )
    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name='itens_periodo',
        verbose_name='Indicador',
    )
    meta = models.DecimalField(
        verbose_name='Meta',
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    resultado = models.DecimalField(
        verbose_name='Resultado',
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Item do período'
        verbose_name_plural = 'Itens do período'
        unique_together = [['periodo', 'indicador']]
        ordering = ['indicador__area', 'indicador__ordem', 'indicador__nome']

    def __str__(self):
        return f'{self.periodo} — {self.indicador.nome}'


ATENDENTES_PADRAO = ['LUCIMEIRE', 'MARIANY', 'NATÁLIA', 'LUANA']


def _pct_int(numerador: int, denominador: int) -> Decimal:
    if not denominador:
        return Decimal('0.00')
    return (Decimal(numerador) / Decimal(denominador) * Decimal('100')).quantize(Decimal('0.01'))


class AtendenteAcademia(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='atendentes_academia',
        verbose_name='Empresa',
    )
    nome = models.CharField(verbose_name='Nome', max_length=120)
    ordem = models.PositiveSmallIntegerField(verbose_name='Ordem', default=0)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Atendente (academia)'
        verbose_name_plural = 'Atendentes (academia)'
        ordering = ['ordem', 'nome']
        unique_together = [['empresa', 'nome']]

    def __str__(self):
        return self.nome


class LancamentoVendasDiario(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='lancamentos_vendas_diario',
        verbose_name='Empresa',
    )
    data = models.DateField(verbose_name='Dia')
    oport_balcao = models.PositiveIntegerField(verbose_name='Oport. balcão', default=0)
    balcao = models.PositiveIntegerField(verbose_name='Balcão', default=0)
    site = models.PositiveIntegerField(verbose_name='Site', default=0)
    total_dia = models.PositiveIntegerField(
        verbose_name='Total vendas dia',
        default=0,
        editable=False,
    )
    cancel_inadimplentes = models.PositiveIntegerField(verbose_name='Inadimplentes', default=0)
    cancel_solicitados = models.PositiveIntegerField(verbose_name='Solicitados', default=0)
    cancel_negassist = models.PositiveIntegerField(verbose_name='Neg. assist.', default=0)
    total_cancel_dia = models.PositiveIntegerField(
        verbose_name='Total cancel. dia',
        default=0,
        editable=False,
    )
    churn_dia = models.DecimalField(
        verbose_name='Churn dia (%)',
        max_digits=7,
        decimal_places=4,
        default=Decimal('0.0000'),
        editable=False,
    )
    conversao_balcao_pct = models.DecimalField(
        verbose_name='Conversão balcão (%)',
        max_digits=7,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False,
    )
    saldo_comercial = models.IntegerField(
        verbose_name='Saldo comercial',
        default=0,
        editable=False,
    )

    class Meta:
        verbose_name = 'Lançamento diário (academia)'
        verbose_name_plural = 'Lançamentos diários (academia)'
        ordering = ['-data']
        unique_together = [['empresa', 'data']]

    def __str__(self):
        return f'{self.data:%d/%m/%Y} — vendas {self.total_dia}'

    def recalcular_derivados(self) -> None:
        if self.pk:
            agg = self.itens_atendente.aggregate(
                oport=Sum('oport'),
                vendas=Sum('vendas'),
                site=Sum('site'),
            )
            self.oport_balcao = agg.get('oport') or 0
            self.balcao = agg.get('vendas') or 0
            self.site = agg.get('site') or 0
        else:
            self.oport_balcao = 0
            self.balcao = 0
            self.site = 0
        self.total_dia = (self.balcao or 0) + (self.site or 0)
        self.total_cancel_dia = (
            (self.cancel_inadimplentes or 0)
            + (self.cancel_solicitados or 0)
            + (self.cancel_negassist or 0)
        )
        self.conversao_balcao_pct = _pct_int(self.balcao or 0, self.oport_balcao or 0)
        self.saldo_comercial = self.total_dia - self.total_cancel_dia
        periodo = obter_periodo_por_data(self.empresa_id, self.data) if self.data else None
        qt_ativos = (periodo.qt_ativos or 0) if periodo else 0
        self.churn_dia = calcular_churn_pct(qt_ativos, self.total_cancel_dia)

    def save(self, *args, **kwargs):
        self.recalcular_derivados()
        super().save(*args, **kwargs)


class ItemAtendenteDiario(models.Model):
    lancamento = models.ForeignKey(
        LancamentoVendasDiario,
        on_delete=models.CASCADE,
        related_name='itens_atendente',
        verbose_name='Lançamento',
    )
    atendente = models.ForeignKey(
        AtendenteAcademia,
        on_delete=models.CASCADE,
        related_name='lancamentos_dia',
        verbose_name='Atendente',
    )
    oport = models.PositiveIntegerField(verbose_name='Oport.', default=0)
    vendas = models.PositiveIntegerField(verbose_name='Vendas', default=0)
    site = models.PositiveIntegerField(verbose_name='Site', default=0)
    cancel = models.PositiveIntegerField(verbose_name='Cancel.', default=0)

    class Meta:
        verbose_name = 'Atendente no dia'
        verbose_name_plural = 'Atendentes no dia'
        unique_together = [['lancamento', 'atendente']]
        ordering = ['atendente__ordem', 'atendente__nome']

    def __str__(self):
        return f'{self.lancamento.data:%d/%m/%Y} — {self.atendente.nome}'


def garantir_atendentes_padrao(empresa_id) -> None:
    if not empresa_id:
        return
    for ordem, nome in enumerate(ATENDENTES_PADRAO, start=1):
        AtendenteAcademia.objects.get_or_create(
            empresa_id=empresa_id,
            nome=nome,
            defaults={'ordem': ordem, 'ativo': True},
        )


def calcular_churn_pct(qt_ativos: int, qt_cancelados: int) -> Decimal:
    if not qt_ativos:
        return Decimal('0.0000')
    pct = (Decimal(qt_cancelados) / Decimal(qt_ativos)) * Decimal('100')
    return pct.quantize(Decimal('0.0001'))


def recalcular_lancamentos_mes(periodo: PeriodoAcademia) -> None:
    """Recalcula churn dos lançamentos diários quando os dados do mês mudam."""
    if not periodo or not periodo.empresa_id:
        return
    campos = [
        'oport_balcao', 'balcao', 'site', 'total_dia',
        'total_cancel_dia', 'churn_dia', 'conversao_balcao_pct', 'saldo_comercial',
    ]
    for lanc in LancamentoVendasDiario.objects.filter(
        empresa_id=periodo.empresa_id,
        data__year=periodo.ano,
        data__month=periodo.mes,
    ):
        lanc.recalcular_derivados()
        lanc.save(update_fields=campos)


def garantir_indicadores_padrao(empresa_id) -> None:
    """Cria indicadores padrão da área se ainda não existirem para a empresa."""
    if not empresa_id:
        return
    for area, nomes in INDICADORES_PADRAO.items():
        for ordem, nome in enumerate(nomes, start=1):
            defaults = {'ordem': ordem, 'ativo': True}
            padrao = PREMIACAO_PROPORCAO_PADRAO.get(nome)
            if padrao:
                _, prem, prop = padrao
                defaults['premiacao'] = prem
                defaults['proporcao'] = prop
            Indicador.objects.get_or_create(
                empresa_id=empresa_id,
                area=area,
                nome=nome,
                defaults=defaults,
            )
