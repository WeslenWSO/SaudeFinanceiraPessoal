import inspect

from django.db import models
from django.db.models import Q

# Django 5.2+: CheckConstraint(condition=...); antes: check=...
_cc_kw = (
    "condition"
    if "condition" in inspect.signature(models.CheckConstraint.__init__).parameters
    else "check"
)
from socio.models import Socio


class RegraRateio(models.Model):
    MODO_PERCENTUAL = 'P'
    MODO_VALOR = 'V'
    MODO_ALOCACAO_CHOICES = (
        (MODO_PERCENTUAL, 'Percentual fixo'),
        (MODO_VALOR, 'Valor na aplicação'),
    )

    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        related_name='regras_rateio',
        verbose_name='Empresa',
    )
    codigo = models.CharField(verbose_name='Código', max_length=30, blank=True, default='')
    nomedaregra = models.CharField(verbose_name='Descrição da regra', max_length=30)
    rateio = models.CharField(
        verbose_name='Rateio',
        max_length=1,
        default='S',
        choices=(
            ('S', 'SIM'),
            ('N', 'NAO'),
        ),
        help_text='SIM: divide o valor entre sócios. NÃO: não gera lançamentos de rateio.',
    )
    modo_alocacao = models.CharField(
        verbose_name='Modo de alocação',
        max_length=1,
        default=MODO_PERCENTUAL,
        choices=MODO_ALOCACAO_CHOICES,
        help_text=(
            'Percentual fixo: usa % cadastrados nos itens. '
            'Valor na aplicação: informe quanto vai para o sócio manual em cada título; o restante fica com o(s) sócio(s) residual.'
        ),
    )

    class Meta:
        verbose_name = 'Regra de rateio'
        verbose_name_plural = 'Regras de rateio'
        ordering = ['empresa_id', 'nomedaregra']
        indexes = [
            models.Index(fields=['empresa', 'nomedaregra']),
        ]

    def __str__(self):
        if self.codigo:
            return f'{self.codigo} — {self.nomedaregra}'
        return self.nomedaregra


class RegraRateioItem(models.Model):
    TIPO_PERCENTUAL = 'P'
    TIPO_MANUAL = 'M'
    TIPO_RESIDUAL = 'R'
    TIPO_PARTICIPACAO_CHOICES = (
        (TIPO_PERCENTUAL, 'Percentual fixo'),
        (TIPO_MANUAL, 'Valor manual na aplicação'),
        (TIPO_RESIDUAL, 'Residual (restante)'),
    )

    regrarateio = models.ForeignKey(RegraRateio, on_delete=models.DO_NOTHING)
    socios = models.ForeignKey(Socio, on_delete=models.DO_NOTHING)
    percRateio = models.DecimalField(default=0.00, verbose_name="Percentual Rateio", null=False, max_digits=5, decimal_places=2)
    tipo_participacao = models.CharField(
        verbose_name='Tipo de participação',
        max_length=1,
        default=TIPO_PERCENTUAL,
        choices=TIPO_PARTICIPACAO_CHOICES,
    )

    def __str__(self):
        return str(self.regrarateio.nomedaregra) or ''


def _meta_observacao_importacao(observacao: str) -> dict[str, str]:
    """Extrai metadados gravados na observação do CAR na importação (registros antigos)."""
    out = {'paciente': '', 'procedimento': '', 'modalidade': '', 'viabilidade': '', 'imp_ln': ''}
    if not observacao:
        return out
    for part in observacao.split('|'):
        p = part.strip()
        if p.startswith('Pac:'):
            out['paciente'] = p[4:].strip()
        elif p.startswith('Proc:'):
            out['procedimento'] = p[5:].strip()
        elif p.startswith('Mod:'):
            out['modalidade'] = p[4:].strip()
        elif p.startswith('Viab:'):
            out['viabilidade'] = p[5:].strip()
        elif p.startswith('ImpLn:') or p.startswith('ImplLn:'):
            out['imp_ln'] = p.split(':', 1)[1].strip()
    return out


def observacao_importacao_com_procedimento(observacao: str, procedimento: str) -> str:
    """Recompõe observação do CAR incluindo Proc: (importações antigas sem procedimento)."""
    obs = (observacao or '').strip()
    proc = (procedimento or '').strip()
    if not obs or not proc or 'Proc:' in obs:
        return obs
    meta = _meta_observacao_importacao(obs)
    parts = []
    if meta['paciente']:
        parts.append(f"Pac:{meta['paciente']}")
    parts.append(f"Proc:{proc[:160]}")
    if meta['modalidade']:
        parts.append(f"Mod:{meta['modalidade']}")
    if meta['viabilidade']:
        parts.append(f"Viab:{meta['viabilidade']}")
    if meta['imp_ln']:
        parts.append(f"ImpLn:{meta['imp_ln']}")
    return '|'.join(parts)


def descricao_rateio_importacao(texto: str) -> str:
    """
    Descrição do rateio importado: Proc + ImpLn.
    Remove Pac, Mod e Viab (já nas colunas Cliente, Modalidade e Viabilidade).
    """
    t = (texto or '').strip()
    if not t:
        return ''
    meta = _meta_observacao_importacao(t)
    parts = []
    if meta['procedimento']:
        parts.append(f"Proc:{meta['procedimento']}")
    if meta['imp_ln']:
        parts.append(f"ImpLn:{meta['imp_ln']}")
    if parts:
        return '|'.join(parts)
    # Texto sem Proc/ImpLn: remove só Pac, Mod e Viab.
    if 'Pac:' not in t and 'Mod:' not in t and 'Viab:' not in t:
        return t
    rest = []
    for part in t.split('|'):
        p = part.strip()
        if not p or p.startswith('Pac:') or p.startswith('Mod:') or p.startswith('Viab:'):
            continue
        rest.append(p)
    return '|'.join(rest)


def descricao_sem_meta_importacao(texto: str) -> str:
    """Alias — preferir descricao_rateio_importacao."""
    return descricao_rateio_importacao(texto)


class LancamentoRateio(models.Model):
    """Linha de rateio gerada a partir de contas a pagar (PGTO, valor negativo) ou a receber (RECEBIMENTO, valor positivo)."""

    TIPO_PGTO = 'PGTO'
    TIPO_RECEBIMENTO = 'RECEBIMENTO'
    TIPO_DEDUCAO_RECEITA = 'DEDUCAO_RECEITA'
    TIPO_CHOICES = [
        (TIPO_PGTO, 'Pagamento'),
        (TIPO_RECEBIMENTO, 'Recebimento'),
        (TIPO_DEDUCAO_RECEITA, 'Dedução da Receita'),
    ]

    ORIGEM_PAGAR = 'PAGAR'
    ORIGEM_RECEBER = 'RECEBER'
    ORIGEM_IMPORTACAO = 'IMPORTACAO'
    ORIGEM_TOTAL_CONVENIO = 'Total Receita USG'
    ORIGEM_CHOICES = (
        (ORIGEM_PAGAR, 'Pagar'),
        (ORIGEM_RECEBER, 'Receber'),
        (ORIGEM_IMPORTACAO, 'IMPORTACAO'),
        (ORIGEM_TOTAL_CONVENIO, 'Total Receita USG'),
    )

    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        verbose_name='Empresa',
        null=True,
        blank=True,
    )
    conta_pagar = models.ForeignKey(
        'contasapagar.ContasaPagar',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lancamentos_rateio',
        verbose_name='Conta a pagar',
    )
    conta_receber = models.ForeignKey(
        'contasareceber.ContaAReceber',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lancamentos_rateio',
        verbose_name='Conta a receber',
    )
    data_pagamento = models.DateField(verbose_name='Data de pagamento / recebimento', null=True, blank=True)
    tipo = models.CharField(verbose_name='Tipo', max_length=20, choices=TIPO_CHOICES)
    descricao = models.CharField(verbose_name='Descrição', max_length=255, blank=True)
    regra_rateio = models.ForeignKey(
        RegraRateio,
        on_delete=models.PROTECT,
        verbose_name='Regra de rateio',
    )
    socio = models.ForeignKey(Socio, on_delete=models.PROTECT, verbose_name='Sócio')
    valor = models.DecimalField(verbose_name='Valor', max_digits=14, decimal_places=2)
    origem = models.CharField(
        verbose_name='Origem',
        max_length=20,
        blank=True,
        default='',
        choices=ORIGEM_CHOICES,
    )
    modalidade = models.CharField(verbose_name='Modalidade', max_length=30, blank=True, default='')
    viabilidade = models.CharField(verbose_name='Viabilidade', max_length=120, blank=True, default='')
    obs = models.CharField(verbose_name='Obs.', max_length=255, blank=True, default='')
    obs_forma = models.CharField(verbose_name='Obs. forma', max_length=120, blank=True, default='')
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        verbose_name = 'Lançamento de rateio'
        verbose_name_plural = 'Lançamentos de rateio'
        ordering = ['-data_pagamento', '-id']
        constraints = [
            models.CheckConstraint(
                **{
                    _cc_kw: (
                        Q(conta_pagar__isnull=False, conta_receber__isnull=True)
                        | Q(conta_pagar__isnull=True, conta_receber__isnull=False)
                        | Q(
                            conta_pagar__isnull=True,
                            conta_receber__isnull=True,
                            origem='Total Receita USG',
                        )
                    )
                },
                name='lancamento_rateio_cap_ou_car',
            ),
        ]
        indexes = [
            models.Index(fields=['empresa', '-data_pagamento']),
            models.Index(fields=['conta_pagar']),
            models.Index(fields=['conta_receber']),
        ]

    def _meta_car(self) -> dict[str, str]:
        if not self.conta_receber_id:
            return _meta_observacao_importacao('')
        return _meta_observacao_importacao(self.conta_receber.observacao or '')

    def origem_exibicao(self) -> str:
        if self.origem:
            return self.get_origem_display()
        if self.conta_pagar_id:
            return 'Pagar'
        if self.conta_receber_id:
            meta = self._meta_car()
            if meta['paciente'] or meta['procedimento']:
                return 'IMPORTACAO'
            return 'Receber'
        return '—'

    def modalidade_exibicao(self) -> str:
        if self.modalidade:
            return self.modalidade
        return self._meta_car().get('modalidade') or '—'

    def descricao_exibicao(self) -> str:
        if self.conta_receber_id:
            car_obs = (self.conta_receber.observacao or '').strip()
            if car_obs and any(tok in car_obs for tok in ('Pac:', 'Proc:', 'ImpLn:', 'ImplLn:')):
                built = descricao_rateio_importacao(car_obs)
                if built:
                    return built
        raw = (self.descricao or '').strip()
        if not raw and self.conta_receber_id:
            raw = (self.conta_receber.doc or '').strip()
        if not raw and self.conta_pagar_id:
            return (self.conta_pagar.descricao or '').strip() or '—'
        if any(tok in raw for tok in ('Pac:', 'Proc:', 'ImpLn:', 'ImplLn:', 'Mod:', 'Viab:')):
            built = descricao_rateio_importacao(raw)
            return built or raw or '—'
        return raw or '—'

    def cliente_exibicao(self) -> str:
        meta = self._meta_car()
        paciente = (meta.get('paciente') or '').strip()
        if not paciente and self.descricao and 'Pac:' in self.descricao:
            paciente = _meta_observacao_importacao(self.descricao).get('paciente', '')
        if not paciente and self.conta_receber_id and self.conta_receber.cliente:
            paciente = (self.conta_receber.cliente or '').strip()
        return paciente or '—'

    def viabilidade_exibicao(self) -> str:
        if self.viabilidade:
            return self.viabilidade
        meta = self._meta_car()
        if meta.get('viabilidade'):
            return meta['viabilidade']
        if self.conta_receber_id and self.conta_receber.cliente:
            return self.conta_receber.cliente[:120]
        return '—'

    def obs_exibicao(self) -> str:
        if self.obs:
            return self.obs
        meta = self._meta_car()
        return meta.get('procedimento') or meta.get('paciente') or '—'

    def obs_rateio_exibicao(self) -> str:
        """Observação informada na edição do rateio; recebimentos importados não usam este campo."""
        obs = (self.obs or '').strip()
        if not obs or self.tipo != self.TIPO_RECEBIMENTO:
            return obs
        if self.origem == self.ORIGEM_IMPORTACAO:
            meta = self._meta_car()
            proc = (meta.get('procedimento') or '').strip()
            pac = (meta.get('paciente') or '').strip()
            if obs == proc or obs == pac:
                return ''
        return obs

    def obs_forma_exibicao(self) -> str:
        if self.obs_forma:
            return self.obs_forma
        if self.conta_receber_id and self.conta_receber.doc:
            return self.conta_receber.doc
        return '—'

    def cobranca_exibicao(self) -> str:
        if self.conta_pagar_id and self.conta_pagar and self.conta_pagar.cobranca_id:
            return self.conta_pagar.cobranca.descricao
        if self.conta_receber_id and self.conta_receber and self.conta_receber.forma_pagamento_id:
            return self.conta_receber.forma_pagamento.descricao
        return '—'

    def _conta_bancaria_obj(self):
        if self.conta_pagar_id and self.conta_pagar and self.conta_pagar.conta_banco_id:
            return self.conta_pagar.conta_banco
        if self.conta_receber_id and self.conta_receber:
            car = self.conta_receber
            if car.conta_banco_id:
                return car.conta_banco
            baixas = getattr(car, 'baixas_ordenadas', None)
            if baixas is not None:
                for baixa in baixas:
                    if baixa.conta_banco_id:
                        return baixa.conta_banco
            from contasareceber.models import BaixaContaAReceber

            baixa = (
                BaixaContaAReceber.objects.filter(
                    conta_a_receber_id=car.pk,
                    conta_banco__isnull=False,
                )
                .select_related('conta_banco', 'conta_banco__banco')
                .order_by('-data_recebimento', '-id')
                .first()
            )
            if baixa and baixa.conta_banco_id:
                return baixa.conta_banco
        return None

    def conta_bancaria_exibicao(self) -> str:
        """Nome curto da conta/caixa (ex.: STONE, BRADESCO)."""
        conta = self._conta_bancaria_obj()
        if not conta:
            return '—'
        return conta.nome_curto()

    def conta_bancaria_completa(self) -> str:
        """Descrição completa da conta (tooltip)."""
        conta = self._conta_bancaria_obj()
        if not conta:
            return '—'
        return str(conta)

    def __str__(self):
        origem = self.conta_pagar_id or self.conta_receber_id
        return f'{self.get_tipo_display()} #{origem} — {self.socio} — {self.valor}'