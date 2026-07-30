from decimal import Decimal
import json

from django.db import models
from django.db.models import Sum

from empresa.models import Empresa


class IndicadorCalculoSicoob(models.Model):
    """
    Catálogo Sicoob — Indicador de Cálculo do extrato de operação de crédito.
    Exemplos: 15-Tabela Price, 3-Sac Decrescente.
    """
    TIPO_CHOICES = [
        ('price', 'Tabela Price'),
        ('sac', 'SAC'),
        ('outro', 'Outro'),
    ]

    codigo = models.PositiveSmallIntegerField(
        unique=True,
        verbose_name='Código Sicoob',
        help_text='Código numérico do indicador no SISBR (ex.: 3, 15).',
    )
    nome = models.CharField(
        max_length=80,
        verbose_name='Nome',
        help_text='Ex.: Tabela Price, Sac Decrescente',
    )
    rotulo = models.CharField(
        max_length=100,
        verbose_name='Rótulo completo',
        help_text='Como aparece no PDF: 15-Tabela Price, 3-Sac Decrescente',
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default='outro',
        verbose_name='Tipo de sistema',
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Indicador de cálculo Sicoob'
        verbose_name_plural = 'Indicadores de cálculo Sicoob'
        ordering = ['codigo']

    def __str__(self):
        return self.rotulo or f'{self.codigo}-{self.nome}'

    @classmethod
    def from_texto_pdf(cls, texto: str):
        """Localiza ou cria indicador a partir do texto do PDF."""
        from .sicoob_pdf import normalizar_indicador_calculo

        rotulo, codigo, nome, tipo = normalizar_indicador_calculo(texto or '')
        if codigo is None:
            return None
        obj, _ = cls.objects.get_or_create(
            codigo=codigo,
            defaults={
                'nome': nome or rotulo,
                'rotulo': rotulo,
                'tipo': tipo,
            },
        )
        # Atualiza rótulo se veio mais completo
        if rotulo and obj.rotulo != rotulo and len(rotulo) >= len(obj.rotulo or ''):
            obj.rotulo = rotulo
            obj.nome = nome or obj.nome
            obj.tipo = tipo or obj.tipo
            obj.save(update_fields=['rotulo', 'nome', 'tipo'])
        return obj


class Emprestimo(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='emprestimos',
        verbose_name='Empresa',
    )
    banco = models.ForeignKey(
        'extrato.Banco',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='emprestimos',
        verbose_name='Banco',
    )
    cooperativa = models.CharField(max_length=200, blank=True, default='')
    cliente = models.CharField(max_length=250, blank=True, default='')
    numero_contrato = models.CharField(max_length=40, verbose_name='Número do Contrato')
    modalidade = models.CharField(max_length=200, blank=True, default='')
    data_operacao = models.DateField(null=True, blank=True)
    data_vencimento = models.DateField(null=True, blank=True)
    prazo_dias = models.PositiveIntegerField(null=True, blank=True)
    valor_contrato = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    valor_tributos = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Tributos',
    )
    valor_tarifas = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Tarifas',
    )
    valor_registros = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Registros',
    )
    valor_servicos_terceiros = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Pagtos. servs. terceiros',
    )
    saldo_devedor_atualizado = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Saldo devedor atualizado',
        help_text='Saldo do PDF na data de emissão do extrato.',
    )
    taxa_juros_am = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0'),
        verbose_name='Taxa juros (% a.m.)',
    )
    taxa_juros_aa = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0'),
        verbose_name='Taxa juros (% a.a.)',
        help_text='Usado em contratos SAC com taxa anual.',
    )
    taxa_multa_am = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0'),
        verbose_name='Taxa multa (% a.m.)',
    )
    taxa_mora_am = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0'),
        verbose_name='Taxa mora (% a.m.)',
    )
    indice_correcao = models.CharField(
        max_length=40, blank=True, default='',
        verbose_name='Índice de correção',
        help_text='Ex.: SELIC',
    )
    indice_correcao_atraso = models.CharField(
        max_length=40, blank=True, default='',
        verbose_name='Índice de correção atraso',
    )
    pct_correcao_am = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0'),
        verbose_name='% de correção (a.m.)',
    )
    pct_correcao_atraso_am = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0'),
        verbose_name='% de correção atraso (a.m.)',
    )
    indicador = models.ForeignKey(
        IndicadorCalculoSicoob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='emprestimos',
        verbose_name='Indicador de cálculo',
    )
    indicador_calculo = models.CharField(
        max_length=80, blank=True, default='',
        verbose_name='Indicador (texto PDF)',
        help_text='Texto bruto importado do extrato.',
    )
    data_extrato = models.DateField(null=True, blank=True, verbose_name='Data do extrato')
    arquivo_origem = models.CharField(max_length=255, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Empréstimo'
        verbose_name_plural = 'Empréstimos'
        ordering = ['-data_operacao', '-id']
        unique_together = [('empresa', 'numero_contrato')]

    def __str__(self):
        return f'Contrato {self.numero_contrato} — {self.cliente or self.cooperativa}'

    @property
    def taxa_calculo_am(self):
        """Referência contratual: juros a.m. + mora a.m. (usada só em parcelas atrasadas)."""
        return (
            (self.taxa_juros_am or Decimal('0'))
            + (self.taxa_mora_am or Decimal('0'))
        ).quantize(Decimal('0.0001'))

    @property
    def valor_total_operacao(self):
        """Valor contrato + tributos + tarifas + registros + serv. terceiros."""
        return (
            (self.valor_contrato or Decimal('0'))
            + (self.valor_tributos or Decimal('0'))
            + (self.valor_tarifas or Decimal('0'))
            + (self.valor_registros or Decimal('0'))
            + (self.valor_servicos_terceiros or Decimal('0'))
        ).quantize(Decimal('0.01'))

    @property
    def indicador_display(self):
        if self.indicador_id:
            return self.indicador.rotulo
        return self.indicador_calculo or '—'

    def parcelas_abertas(self):
        return self.parcelas.filter(status='aberta')

    def valor_parcela_do_extrato(self):
        """
        Valor da parcela conforme o extrato importado.
        Price: parcela fixa (1ª aberta ou última paga com valor).
        SAC: valor da próxima parcela aberta.
        """
        parcelas = list(self.parcelas.all())
        abertas = sorted(
            (p for p in parcelas if p.status == 'aberta'),
            key=lambda p: p.numero or 0,
        )
        for p in abertas:
            if (p.valor_parcela or Decimal('0')) > 0:
                return (p.valor_parcela or Decimal('0')).quantize(Decimal('0.01'))
        pagas = sorted(
            (p for p in parcelas if p.status == 'paga'),
            key=lambda p: p.numero or 0,
            reverse=True,
        )
        for p in pagas:
            if (p.valor_parcela or Decimal('0')) > 0:
                return (p.valor_parcela or Decimal('0')).quantize(Decimal('0.01'))
        return Decimal('0.00')

    def total_aberto(self):
        return (
            self.parcelas_abertas().aggregate(t=Sum('valor_parcela'))['t']
            or Decimal('0')
        )

    def total_amortizacao_aberta(self):
        return (
            self.parcelas_abertas().aggregate(t=Sum('amortizacao'))['t']
            or Decimal('0')
        )

    def total_juros_aberto(self):
        return (
            self.parcelas_abertas().aggregate(t=Sum('juros'))['t']
            or Decimal('0')
        )


class ParcelaEmprestimo(models.Model):
    STATUS_CHOICES = [
        ('aberta', 'Em aberto'),
        ('paga', 'Paga'),
        ('quitada', 'Quitada (simulação)'),
    ]

    emprestimo = models.ForeignKey(
        Emprestimo,
        on_delete=models.CASCADE,
        related_name='parcelas',
        verbose_name='Empréstimo',
    )
    numero = models.PositiveIntegerField(verbose_name='Nº parcela')
    data_vencimento = models.DateField()
    valor_parcela = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    amortizacao = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    juros = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    data_pagamento = models.DateField(null=True, blank=True)
    historico = models.CharField(max_length=200, blank=True, default='')
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    mora = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    multa = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Multa (atraso)',
    )
    iof = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    correcao = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        verbose_name='Correção (SAC)',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aberta')

    class Meta:
        verbose_name = 'Parcela de empréstimo'
        verbose_name_plural = 'Parcelas de empréstimo'
        ordering = ['numero']
        unique_together = [('emprestimo', 'numero')]

    def __str__(self):
        return f'{self.emprestimo.numero_contrato} — parcela {self.numero}'

    @property
    def is_aberta(self):
        return self.status == 'aberta'

    def situacao_cobranca(self, data_ref=None):
        from django.utils import timezone

        from .taxas_parcela import situacao_parcela_aberta

        ref = data_ref or timezone.localdate()
        return situacao_parcela_aberta(self, ref)

    def taxa_juros_efetiva_am(self, data_ref=None):
        from django.utils import timezone

        from .taxas_parcela import taxa_juros_am_parcela

        ref = data_ref or timezone.localdate()
        emp = self.emprestimo
        return taxa_juros_am_parcela(
            self,
            taxa_juros_am=emp.taxa_juros_am or Decimal('0'),
            taxa_mora_am=emp.taxa_mora_am or Decimal('0'),
            data_ref=ref,
        )

    def multa_atraso_calculada(self, data_ref=None):
        from django.utils import timezone

        from .taxas_parcela import multa_atraso_parcela

        ref = data_ref or timezone.localdate()
        return multa_atraso_parcela(self, ref)

    @property
    def taxa_mil(self):
        """
        Taxa percentual: (juros / valor_pago) * 100.
        Se não houver valor pago, usa o valor da parcela.
        """
        base = self.valor_pago if self.valor_pago not in (None, Decimal('0')) else self.valor_parcela
        if not base:
            return None
        return (self.juros or Decimal('0')) / base * Decimal('100')

    def marcar_paga_do_extrato(self):
        """Define status pago quando o PDF traz data de pagamento."""
        if self.data_pagamento:
            self.status = 'paga'
        else:
            self.status = 'aberta'


class SimulacaoQuitacaoEmprestimo(models.Model):
    """Simulação de quitação salva para consulta posterior."""

    emprestimo = models.ForeignKey(
        Emprestimo,
        on_delete=models.CASCADE,
        related_name='simulacoes_quitacao',
        verbose_name='Empréstimo',
    )
    titulo = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Título / observação',
        help_text='Opcional — facilita a pesquisa.',
    )
    data_quitacao = models.DateField(verbose_name='Data pretendida de quitação')
    metodo = models.CharField(max_length=20, blank=True, default='', verbose_name='Método')
    indicador_rotulo = models.CharField(max_length=100, blank=True, default='')
    parcelas_numeros = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Nºs das parcelas',
        help_text='Ex.: 19,20,21',
    )
    qtd_parcelas = models.PositiveIntegerField(default=0)
    total_amortizacao = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_parcela_original = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Soma parcelas originais',
        help_text='Soma do valor de face das parcelas selecionadas (antes da quitação).',
    )
    total_juros_extrato = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    juros_calculado = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    valor_quitacao = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    dias_juros = models.PositiveIntegerField(default=0)
    data_referencia = models.DateField(null=True, blank=True)
    data_fim_juros = models.DateField(null=True, blank=True)
    parcelas_restantes = models.PositiveIntegerField(default=0)
    saldo_restante_amort = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    detalhes_json = models.TextField(blank=True, default='', verbose_name='Detalhes (JSON)')
    criado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulacoes_quitacao_emprestimo',
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Simulação de quitação'
        verbose_name_plural = 'Simulações de quitação'
        ordering = ['-criado_em']

    def __str__(self):
        return (
            f'{self.emprestimo.numero_contrato} — '
            f'{self.data_quitacao} — R$ {self.valor_quitacao}'
        )

    @property
    def juros_quitacao(self):
        """Juros da quitação = valor quitação − principal (ou campo gravado)."""
        j = self.juros_calculado or Decimal('0')
        if j > 0:
            return j.quantize(Decimal('0.01'))
        principal = self.total_amortizacao or Decimal('0')
        quitacao = self.valor_quitacao or Decimal('0')
        return max(Decimal('0'), (quitacao - principal).quantize(Decimal('0.01')))

    @property
    def diferenca(self):
        """Economia = parcelas originais − valor para quitação."""
        original = self.total_parcela_original or Decimal('0')
        if original <= 0 and self.detalhes_json:
            try:
                d = json.loads(self.detalhes_json)
                original = Decimal(str(d.get('total_parcela_original') or 0))
            except Exception:
                original = Decimal('0')
        return (original - (self.valor_quitacao or Decimal('0'))).quantize(Decimal('0.01'))

    @property
    def parcela_original_efetiva(self):
        if (self.total_parcela_original or Decimal('0')) > 0:
            return self.total_parcela_original
        if self.detalhes_json:
            try:
                d = json.loads(self.detalhes_json)
                return Decimal(str(d.get('total_parcela_original') or 0)).quantize(Decimal('0.01'))
            except Exception:
                pass
        return Decimal('0.00')

    def _detalhes(self):
        if not self.detalhes_json:
            return {}
        try:
            d = json.loads(self.detalhes_json)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @property
    def sim_parcial(self):
        sp = self._detalhes().get('sim_parcial')
        return sp if isinstance(sp, dict) else {}

    @property
    def novo_saldo_devedor(self):
        sp = self.sim_parcial
        if sp.get('novo_saldo') not in (None, '', 0, '0'):
            try:
                return Decimal(str(sp.get('novo_saldo'))).quantize(Decimal('0.01'))
            except Exception:
                pass
        if (self.saldo_restante_amort or Decimal('0')) > 0 and self.sim_parcial:
            return self.saldo_restante_amort
        return Decimal('0.00')

    @property
    def nova_parcela(self):
        sp = self.sim_parcial
        try:
            return Decimal(str(sp.get('nova_parcela') or 0)).quantize(Decimal('0.01'))
        except Exception:
            return Decimal('0.00')

    @property
    def valor_parcela_extrato(self):
        """Valor da parcela do extrato do contrato (não da simulação parcial)."""
        v = self._dec_detalhe('valor_parcela_extrato')
        if v > 0:
            return v
        v_ref = self._dec_detalhe('valor_parcela_ref')
        if v_ref > 0:
            return v_ref
        try:
            return self.emprestimo.valor_parcela_do_extrato()
        except Exception:
            return Decimal('0.00')

    @property
    def n_restante_parcial(self):
        sp = self.sim_parcial
        try:
            n = int(sp.get('n_restante') or 0)
            if n > 0:
                return n
        except Exception:
            pass
        return self.parcelas_restantes or 0

    @property
    def remanescentes_rotulo(self):
        sp = self.sim_parcial
        rot = (sp.get('n_restante_rotulo') or '').strip()
        if rot:
            return rot
        n = self.n_restante_parcial
        ini = sp.get('num_inicio')
        fim = sp.get('num_fim')
        if n and ini and fim:
            return f'{n} parcela{"s" if n != 1 else ""} ({ini}…{fim})'
        if n:
            return f'{n} parcela{"s" if n != 1 else ""}'
        return '—'

    def _dec_detalhe(self, *keys, default='0'):
        d = self._detalhes()
        cur = d
        for k in keys:
            if not isinstance(cur, dict):
                return Decimal(default).quantize(Decimal('0.01'))
            cur = cur.get(k)
        try:
            return Decimal(str(cur if cur not in (None, '') else default)).quantize(Decimal('0.01'))
        except Exception:
            return Decimal(default).quantize(Decimal('0.01'))

    @property
    def principal_contrato(self):
        v = self._dec_detalhe('quitacao_contrato', 'valor_principal')
        if v > 0:
            return v
        return Decimal('0.00')

    @property
    def face_contrato(self):
        v = self._dec_detalhe('quitacao_contrato', 'valor_parcela_original')
        if v > 0:
            return v
        return Decimal('0.00')

    @property
    def juros_contrato(self):
        v = self._dec_detalhe('quitacao_contrato', 'juros')
        if v > 0:
            return v
        principal = self.principal_contrato
        quitacao = self.quitacao_contrato
        if quitacao > 0 and principal > 0:
            return max(Decimal('0'), (quitacao - principal).quantize(Decimal('0.01')))
        return Decimal('0.00')

    @property
    def quitacao_contrato(self):
        v = self._dec_detalhe('quitacao_contrato', 'valor_quitacao')
        if v > 0:
            return v
        # Se a simulação já era do contrato inteiro, usa o valor salvo
        if not self.sim_parcial and (self.valor_quitacao or Decimal('0')) > 0:
            return self.valor_quitacao
        return Decimal('0.00')

    @property
    def diferenca_contrato(self):
        face = self.face_contrato
        quitacao = self.quitacao_contrato
        d = self._dec_detalhe('quitacao_contrato', 'diferenca')
        if face > 0 or quitacao > 0:
            return (face - quitacao).quantize(Decimal('0.01'))
        if d != 0:
            return d
        return Decimal('0.00')
