import re
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# Create your models here.
class Empresa(models.Model):
    STATUS_CHOICES = [
        ('Ativa', 'Ativa'),
        ('Inativa', 'Inativa'),
    ]
    razao = models.CharField(verbose_name='Razao', max_length=50)
    cnpj = models.CharField(verbose_name='CNPJ', max_length=14)
    status = models.CharField(
        verbose_name='Estatus',
        max_length=7,
        choices=STATUS_CHOICES,
        default='Ativa'
    )
    nome_fantasia = models.CharField(verbose_name='Nome Fantasia', max_length=100, blank=True, null=True)
    endereco = models.TextField(verbose_name='Endereço', blank=True, null=True)
    telefone = models.CharField(verbose_name='Telefone', max_length=20, blank=True, null=True)
    email = models.EmailField(verbose_name='Email', blank=True, null=True)
    usa_base_calculo_reduzido = models.BooleanField(verbose_name='Usa Base de Cálculo Reduzido', default=False)
    utiliza_iss_fixo = models.BooleanField(verbose_name='Utiliza ISS Fixo', default=False)

    REGIME_TRIBUTARIO_CHOICES = [
        ('LUCRO_REAL', 'Lucro Real'),
        ('LUCRO_PRESUMIDO', 'Lucro Presumido'),
        ('SIMPLES_NACIONAL', 'Simples Nacional'),
    ]
    regime_tributario = models.CharField(
        verbose_name='Regime Tributário',
        max_length=20,
        choices=REGIME_TRIBUTARIO_CHOICES,
        default='LUCRO_REAL',
        blank=True,
        null=True
    )

    TIPO_APURACAO_CHOICES = [
        ('CAIXA', 'Caixa'),
        ('COMPETENCIA', 'Competência'),
    ]
    tipo_apuracao = models.CharField(
        verbose_name='Tipo de Apuração',
        max_length=15,
        choices=TIPO_APURACAO_CHOICES,
        default='COMPETENCIA',
        blank=True,
        null=True
    )

    # Campos específicos para Simples Nacional
    anexo_i = models.BooleanField(verbose_name='Anexo I', default=False)
    anexo_ii = models.BooleanField(verbose_name='Anexo II', default=False)
    anexo_iii = models.BooleanField(verbose_name='Anexo III', default=False)
    anexo_iv = models.BooleanField(verbose_name='Anexo IV', default=False)
    anexo_v = models.BooleanField(verbose_name='Anexo V', default=False)
    tem_fator_r = models.BooleanField(
        verbose_name='Possui Fator R',
        default=False,
        help_text='Apenas para Anexos III e V'
    )

    codigo_externo = models.CharField(verbose_name='Código Externo', max_length=50, blank=True, null=True, help_text='Código externo para integração com outros sistemas')
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['razao']

    def __str__(self):
        return self.razao

class UsuarioEmpresa(models.Model):
    """Relacionamento entre usuário e empresa (notasfiscais). Evite conflito com empresa.UsuarioEmpresa via related_name."""
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Usuário',
        related_name='notasfiscais_usuarioempresa_set',
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    representante_legal = models.CharField(
        verbose_name="Representante Legal",
        max_length=255,
        blank=True,
        default="",
    )
    pais = models.CharField(
        verbose_name="País",
        max_length=100,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = 'Usuário Empresa'
        verbose_name_plural = 'Usuários Empresas'
        unique_together = ['usuario', 'empresa']
        ordering = ['usuario', 'empresa']

    def __str__(self):
        return f"{self.usuario.username} - {self.empresa.razao}"


class NotaFiscalServico(models.Model):
    """Nota Fiscal de Serviço (NFSe). FK empresa referencia empresa.Empresa."""
    STATUS_CONCILIACAO_CHOICES = [
        ('nao_conciliado', 'Não Conciliado'),
        ('conciliado', 'Conciliado'),
        ('parcialmente_conciliado', 'Parcialmente Conciliado'),
    ]
    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        verbose_name='Empresa',
        null=True,
        blank=True,
    )
    numero_nota = models.CharField(verbose_name='Número da Nota', max_length=20)
    serie = models.CharField(verbose_name='Série', max_length=10)
    numero_dps = models.CharField(
        verbose_name='Número da DPS',
        max_length=20,
        blank=True,
        null=True,
        help_text='Número da DPS no XML nacional (nDPS); não confundir com o nNFSe no DANFSE.',
    )
    data_emissao = models.DateField(verbose_name='Data de Emissão', default=timezone.now)
    cnpj_cpf = models.CharField(verbose_name='CNPJ/CPF', max_length=18)
    cliente = models.CharField(verbose_name='Cliente', max_length=200)
    valor_bruto = models.DecimalField(verbose_name='Valor Bruto', max_digits=15, decimal_places=2)
    valor_liquido = models.DecimalField(verbose_name='Valor Líquido', max_digits=15, decimal_places=2)
    valor_deducoes = models.DecimalField(verbose_name='Valor Deduções', max_digits=10, decimal_places=2, default=0)
    valor_pis = models.DecimalField(verbose_name='Valor PIS', max_digits=10, decimal_places=2, default=0)
    valor_cofins = models.DecimalField(verbose_name='Valor COFINS', max_digits=10, decimal_places=2, default=0)
    valor_inss = models.DecimalField(verbose_name='Valor INSS', max_digits=10, decimal_places=2, default=0)
    valor_ir = models.DecimalField(verbose_name='Valor IR', max_digits=10, decimal_places=2, default=0)
    valor_csll = models.DecimalField(verbose_name='Valor CSLL', max_digits=10, decimal_places=2, default=0)
    iss_retido = models.BooleanField(verbose_name='ISS Retido', default=False)
    valor_iss_retido = models.DecimalField(verbose_name='Valor ISS Retido', max_digits=10, decimal_places=2, default=0)
    outras_retencoes = models.DecimalField(verbose_name='Outras Retenções', max_digits=10, decimal_places=2, default=0)
    aliquota = models.DecimalField(verbose_name='Alíquota (%)', max_digits=5, decimal_places=2, default=0)
    socio = models.ForeignKey(
        'socio.Socio',
        verbose_name='Sócio Responsável',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    discriminacao = models.TextField(verbose_name='Discriminação', blank=True, null=True)
    observacoes = models.TextField(verbose_name='Observações', blank=True, null=True)
    segmento = models.CharField(verbose_name='Segmento', max_length=100, blank=True, null=True)
    base_servico = models.CharField(
        verbose_name='Base Serviço',
        max_length=10,
        choices=[('NORMAL', 'Normal'), ('DEMAIS', 'Demais')],
        default='NORMAL',
    )
    data_cancelamento = models.DateField(verbose_name='Data de Cancelamento', null=True, blank=True)
    codigo_motivo_cancelamento = models.CharField(
        verbose_name='Código motivo cancelamento',
        max_length=10,
        blank=True,
        default='',
    )
    motivo_cancelamento = models.TextField(
        verbose_name='Motivo do cancelamento',
        blank=True,
        default='',
    )
    forma_pagamento = models.ForeignKey(
        'cobranca.Cobranca',
        verbose_name='Forma de Pagamento',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    nsu = models.CharField(verbose_name='NSU', max_length=100, blank=True, null=True)
    status_conciliacao = models.CharField(
        verbose_name='Status de Conciliação',
        max_length=30,
        choices=STATUS_CONCILIACAO_CHOICES,
        default='nao_conciliado',
        null=True,
        blank=True,
    )
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)
    issapuracao = models.DecimalField(verbose_name='Iss Apuração', max_digits=10, decimal_places=2, default=0)
    pisapuracao = models.DecimalField(verbose_name='Pis Apuração', max_digits=10, decimal_places=2, default=0)
    cofinsapuracao = models.DecimalField(verbose_name='Cofins Apuração', max_digits=10, decimal_places=2, default=0)
    csllapuracao = models.DecimalField(verbose_name='Csll Apuração', max_digits=10, decimal_places=2, default=0)
    irpjapuracao = models.DecimalField(verbose_name='Irpj Apuração', max_digits=10, decimal_places=2, default=0)
    irpjadicional = models.DecimalField(verbose_name='Irpj Adicional', max_digits=10, decimal_places=2, default=0)
    codigo_da_regra_do_imposto = models.ForeignKey(
        'regraImposto.RegraImposto',
        verbose_name='Código da Regra do Imposto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    valor_recebido = models.DecimalField(
        verbose_name='Valor Recebido',
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True,
    )
    base_ibs_cbs = models.DecimalField(
        verbose_name='Base IBS/CBS',
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text='Base de cálculo IBS/CBS (reforma tributária), tag vBC do XML.',
    )
    valor_ibs = models.DecimalField(
        verbose_name='Valor IBS',
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text='Valor do IBS destacado no XML nacional (vIBS / vIBSTot).',
    )
    valor_cbs = models.DecimalField(
        verbose_name='Valor CBS',
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text='Valor da CBS destacada no XML nacional (vCBS / vCBSTot).',
    )
    aliquota_ibs = models.DecimalField(
        verbose_name='Alíquota IBS (%)',
        max_digits=7,
        decimal_places=4,
        default=0,
    )
    aliquota_cbs = models.DecimalField(
        verbose_name='Alíquota CBS (%)',
        max_digits=7,
        decimal_places=4,
        default=0,
    )

    class Meta:
        verbose_name = 'Nota Fiscal de Serviço'
        verbose_name_plural = 'Notas Fiscais de Serviço'
        ordering = ['-data_emissao', '-numero_nota']
        unique_together = [('empresa', 'numero_nota', 'serie')]

    def __str__(self):
        return f"NFSe {self.numero_nota} - {self.cliente} - R$ {self.valor_liquido}"

    def get_valor_pendente(self):
        """Retorna o valor pendente de recebimento"""
        return self.valor_liquido

    @property
    def valor_liquido_depois_da_apuracao(self):
        """Valor líquido após descontar todos os impostos de apuração (Total a Distribuir)."""
        from decimal import Decimal
        valor_bruto = self.valor_bruto or Decimal('0')
        pis = self.pisapuracao or Decimal('0')
        cofins = self.cofinsapuracao or Decimal('0')
        iss = self.issapuracao or Decimal('0')
        csll = self.csllapuracao or Decimal('0')
        irpj = self.irpjapuracao or Decimal('0')
        adicional = self.irpjadicional or Decimal('0')
        total_impostos = pis + cofins + iss + csll + irpj + adicional
        return valor_bruto - total_impostos

    def is_pago(self):
        """Verifica se a nota está paga"""
        return False

    def is_cancelada(self):
        """Verifica se a nota está cancelada"""
        return self.data_cancelamento is not None

    @property
    def extracted_autorizacao(self):
        """Autorização do cartão: campo nsu ou extraída da discriminação (AUT / STONE ID)."""
        nsu = (self.nsu or '').strip()
        if nsu:
            return nsu
        if self.discriminacao:
            from notasfiscais.utils import extrair_autorizacao
            return extrair_autorizacao(self.discriminacao)
        return None

    def autorizacao_para_conta_receber(self):
        return self.extracted_autorizacao

    def extract_payment_method_from_description(self):
        """Extrai a forma de pagamento da discriminação"""
        if not self.discriminacao:
            return None
        discriminacao_upper = self.discriminacao.upper()
        if 'PGT: DEBITO' in discriminacao_upper or 'PAGAMENTO: CD' in discriminacao_upper or 'FORMA DE PAGAMENTO: CD' in discriminacao_upper or 'FORMA DE PAGAMENTO (CD)' in discriminacao_upper or 'FORMA DE PAGAMENTO P(CD)' in discriminacao_upper or re.search(r'FORMA DE PAGAMENTO\s+CD\b', discriminacao_upper):
            return 'CARTAO DEBITO'
        if 'PGT: CREDITO' in discriminacao_upper or 'PAGAMENTO: CC' in discriminacao_upper or 'FORMA DE PAGAMENTO: CC' in discriminacao_upper or 'FORMA DE PAGAMENTO (CC)' in discriminacao_upper or 'FORMA DE PAGAMENTO P(CC)' in discriminacao_upper or re.search(r'FORMA DE PAGAMENTO\s+CC\b', discriminacao_upper):
            return 'CARTAO CREDITO'
        if re.search(
            r'FORMA\s+DE\s+PAGAMENTO\s*:\s*(?:[\d.,\s]+\s*)?CD\b',
            self.discriminacao or '',
            re.IGNORECASE,
        ):
            return 'CARTAO DEBITO'
        if re.search(
            r'FORMA\s+DE\s+PAGAMENTO\s*:\s*(?:[\d.,\s]+\s*)?CC\b',
            self.discriminacao or '',
            re.IGNORECASE,
        ):
            return 'CARTAO CREDITO'
        # PIX antes de dinheiro: textos como "FORMA DE PAGAMENTO:600 PIX" não contêm ": PIX" literal
        if re.search(
            r'FORMA\s+DE\s+PAGAMENTO\s*:\s*(?:\d+[.\s\-/_]*)?PIX\b',
            self.discriminacao or '',
            re.IGNORECASE,
        ):
            return 'PIX'
        if 'FORMA DE PAGAMENTO: DH' in discriminacao_upper or 'FORMA DE PAGAMENTO: DINHEIRO' in discriminacao_upper:
            return 'DINHEIRO'
        if 'FORMA DE PAGAMENTO: PIX' in discriminacao_upper:
            return 'PIX'
        if 'FORMA DE PAGAMENTO: BOLETO' in discriminacao_upper:
            return 'BOLETO'
        return None

    def get_tipo_servico(self):
        """Determina o tipo de serviço baseado na discriminação"""
        if not self.discriminacao:
            return 'DESCONHECIDO'
        d = self.discriminacao.lower()
        if 'exame' in d:
            return 'EXAME'
        if 'cirurgia' in d or 'cirurgi' in d:
            return 'CIRURGIA'
        if 'procedimento' in d or 'proced' in d:
            return 'PROCEDIMENTO'
        if 'consulta' in d or 'consult' in d:
            return 'CONSULTA'
        return 'DESCONHECIDO'

    def determinar_base_servico(self):
        """Determina a base de serviço baseada na configuração da empresa"""
        if not self.empresa:
            return 'NORMAL'
        if not getattr(self.empresa, 'usa_base_calculo_reduzido', False):
            return 'NORMAL'
        tipo_servico = self.get_tipo_servico()
        if tipo_servico in ['EXAME', 'CIRURGIA', 'PROCEDIMENTO']:
            return 'DEMAIS'
        return 'NORMAL'

    def calcular_iss_apuracao(self):
        if not self.codigo_da_regra_do_imposto or not self.valor_bruto or not self.empresa:
            return 0
        if getattr(self.empresa, 'utiliza_iss_fixo', False):
            return 0
        aliquota_iss = self.codigo_da_regra_do_imposto.aliquota_iss_apuracao or 0
        if aliquota_iss > 0:
            return (self.valor_bruto * aliquota_iss) / 100 - (self.valor_iss_retido or 0)
        return 0

    def calcular_pis_apuracao(self):
        if not self.codigo_da_regra_do_imposto or not self.valor_bruto:
            return 0
        aliquota_pis = self.codigo_da_regra_do_imposto.aliquota_pis or 0
        return self.valor_bruto * (aliquota_pis / 100) - (self.valor_pis or 0)

    def calcular_cofins_apuracao(self):
        if not self.codigo_da_regra_do_imposto or not self.valor_bruto:
            return 0
        aliquota_cofins = self.codigo_da_regra_do_imposto.aliquota_cofins or 0
        return self.valor_bruto * (aliquota_cofins / 100) - (self.valor_cofins or 0)

    def calcular_csll_apuracao(self):
        if not self.codigo_da_regra_do_imposto or not self.valor_bruto:
            return 0
        aliquota_csll = self.codigo_da_regra_do_imposto.aliquota_csll or 0
        return self.valor_bruto * (aliquota_csll / 100) - (self.valor_csll or 0)

    def calcular_irpj_apuracao(self):
        if not self.codigo_da_regra_do_imposto or not self.valor_bruto:
            return 0
        aliquota_irpj = self.codigo_da_regra_do_imposto.aliquota_irpj or 0
        return self.valor_bruto * (aliquota_irpj / 100) - (self.valor_ir or 0)

    def gerar_contas_a_receber(self):
        from decimal import Decimal

        from contasareceber.models import ContaAReceber

        if not self.pk or not self.forma_pagamento:
            return
        if self.is_cancelada():
            return
        vl = self.valor_liquido
        if vl is None or vl <= Decimal('0'):
            return
        if ContaAReceber.objects.filter(nota_id=self.pk).exists():
            auth = self.autorizacao_para_conta_receber()
            if auth:
                ContaAReceber.objects.filter(nota_id=self.pk).filter(
                    models.Q(autorizacao__isnull=True) | models.Q(autorizacao='')
                ).update(autorizacao=auth)
            return
        data_vencimento = self.data_emissao
        if hasattr(self.forma_pagamento, 'formapgto') and self.forma_pagamento.formapgto == '1':
            intervalo_dias = int(getattr(self.forma_pagamento, 'intervaloparcelas', 0) or 0)
            data_vencimento = self.data_emissao + timezone.timedelta(days=intervalo_dias)
        ContaAReceber.objects.create(
            empresa=self.empresa,
            nota=self,
            cliente=self.cliente,
            cnpj_cpf=self.cnpj_cpf,
            data_emissao=self.data_emissao,
            data_vencimento=data_vencimento,
            valor_a_receber=self.valor_liquido,
            parcela='1/1',
            doc=self.numero_nota,
            autorizacao=self.autorizacao_para_conta_receber(),
            forma_pagamento=self.forma_pagamento,
            observacao=self.discriminacao or f'Nota Fiscal {self.numero_nota}',
        )

    # Campos cuja alteração pode exigir criar título em CAR (save parcial com update_fields)
    _CAMPOS_DISPARAM_GERACAO_CONTA_RECEBER = frozenset({
        'forma_pagamento', 'forma_pagamento_id',
        'valor_liquido', 'valor_bruto', 'data_emissao',
        'cliente', 'cnpj_cpf', 'numero_nota', 'serie', 'discriminacao',
        'empresa', 'empresa_id',
        'data_cancelamento', 'nsu',
    })

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if not self.base_servico or self.base_servico == 'NORMAL':
            self.base_servico = self.determinar_base_servico()
        if not self.forma_pagamento and self.discriminacao:
            payment_method = self.extract_payment_method_from_description()
            if payment_method:
                try:
                    from cobranca.models import Cobranca
                    forma_pgto = Cobranca.objects.get(descricao=payment_method)
                    self.forma_pagamento = forma_pgto
                except (Cobranca.DoesNotExist, Exception):
                    pass
        if self.discriminacao and not (self.nsu or '').strip():
            from notasfiscais.utils import extrair_autorizacao
            auth = extrair_autorizacao(self.discriminacao)
            if auth:
                self.nsu = auth
                if update_fields is not None:
                    kwargs['update_fields'] = list(set(update_fields) | {'nsu'})
        self.issapuracao = self.calcular_iss_apuracao()
        self.pisapuracao = self.calcular_pis_apuracao()
        self.cofinsapuracao = self.calcular_cofins_apuracao()
        self.csllapuracao = self.calcular_csll_apuracao()
        self.irpjapuracao = self.calcular_irpj_apuracao()
        super().save(*args, **kwargs)
        # Evita rodar gerar_contas_a_receber em saves só com sócio/conciliação/etc. (duplicava título CAR)
        if update_fields is not None:
            if not set(update_fields) & self._CAMPOS_DISPARAM_GERACAO_CONTA_RECEBER:
                return
        self.gerar_contas_a_receber()
        if self.pk:
            from contasareceber.socio_sync import (
                propagar_autorizacao_nota_para_contas_receber,
                propagar_forma_pagamento_nota_para_contas_receber,
            )

            propagar_forma_pagamento_nota_para_contas_receber(self)
            propagar_autorizacao_nota_para_contas_receber(self)


class LogNotaFiscal(models.Model):
    """
    Cópia de segurança da NFSe antes de exclusão ou segmentação (histórico).
    A tabela foi recriada após remoção acidental em migrações antigas; mantém compatibilidade
    com segmentação e restauração.
    """
    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        verbose_name='Empresa',
    )
    numero_nota = models.CharField(verbose_name='Número da Nota', max_length=20)
    serie = models.CharField(verbose_name='Série', max_length=10, blank=True, null=True)
    data_emissao = models.DateField(verbose_name='Data de Emissão', default=timezone.now)
    cnpj_cpf = models.CharField(verbose_name='CNPJ/CPF', max_length=18)
    cliente = models.CharField(verbose_name='Cliente', max_length=200)
    valor_bruto = models.DecimalField(verbose_name='Valor Bruto', max_digits=10, decimal_places=2)
    valor_liquido = models.DecimalField(verbose_name='Valor Líquido', max_digits=10, decimal_places=2)
    valor_deducoes = models.DecimalField(verbose_name='Valor Deduções', max_digits=10, decimal_places=2, default=0)
    valor_pis = models.DecimalField(verbose_name='Valor PIS', max_digits=10, decimal_places=2, default=0)
    valor_cofins = models.DecimalField(verbose_name='Valor COFINS', max_digits=10, decimal_places=2, default=0)
    valor_inss = models.DecimalField(verbose_name='Valor INSS', max_digits=10, decimal_places=2, default=0)
    valor_ir = models.DecimalField(verbose_name='Valor IR', max_digits=10, decimal_places=2, default=0)
    valor_csll = models.DecimalField(verbose_name='Valor CSLL', max_digits=10, decimal_places=2, default=0)
    iss_retido = models.BooleanField(verbose_name='ISS Retido', default=False)
    valor_iss_retido = models.DecimalField(verbose_name='Valor ISS Retido', max_digits=10, decimal_places=2, default=0)
    outras_retencoes = models.DecimalField(verbose_name='Outras Retenções', max_digits=10, decimal_places=2, default=0)
    aliquota = models.DecimalField(verbose_name='Alíquota (%)', max_digits=5, decimal_places=2, default=0)
    socio = models.ForeignKey(
        'socio.Socio',
        verbose_name='Sócio Responsável',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    discriminacao = models.TextField(verbose_name='Discriminação', blank=True, null=True)
    observacoes = models.TextField(verbose_name='Observações', blank=True, null=True)
    segmento = models.CharField(verbose_name='Segmento', max_length=100, blank=True, null=True)
    base_servico = models.CharField(
        verbose_name='Base Serviço',
        max_length=10,
        choices=[('NORMAL', 'Normal'), ('DEMAIS', 'Demais')],
        default='NORMAL',
    )
    forma_pagamento = models.ForeignKey(
        'cobranca.Cobranca',
        verbose_name='Forma de Pagamento',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    nsu = models.CharField(verbose_name='NSU', max_length=100, blank=True, null=True)
    status_conciliacao = models.CharField(
        verbose_name='Status de Conciliação',
        max_length=30,
        choices=NotaFiscalServico.STATUS_CONCILIACAO_CHOICES,
        default='nao_conciliado',
        null=True,
        blank=True,
    )
    issapuracao = models.DecimalField(verbose_name='Iss Apuração', max_digits=10, decimal_places=2, default=0)
    pisapuracao = models.DecimalField(verbose_name='Pis Apuração', max_digits=10, decimal_places=2, default=0)
    cofinsapuracao = models.DecimalField(verbose_name='Cofins Apuração', max_digits=10, decimal_places=2, default=0)
    csllapuracao = models.DecimalField(verbose_name='Csll Apuração', max_digits=10, decimal_places=2, default=0)
    irpjapuracao = models.DecimalField(verbose_name='Irpj Apuração', max_digits=10, decimal_places=2, default=0)
    irpjadicional = models.DecimalField(verbose_name='Irpj Adicional', max_digits=10, decimal_places=2, default=0)
    codigo_da_regra_do_imposto = models.ForeignKey(
        'regraImposto.RegraImposto',
        verbose_name='Código da Regra do Imposto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    motivo_exclusao = models.CharField(
        verbose_name='Motivo da Exclusão',
        max_length=100,
        default='segmentacao',
        blank=True,
    )
    usuario_segmentacao = models.ForeignKey(
        User,
        verbose_name='Usuário que segmentou',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    data_segmentacao = models.DateTimeField(verbose_name='Data da Segmentação', auto_now_add=True)

    class Meta:
        verbose_name = 'Log Nota Fiscal'
        verbose_name_plural = 'Logs Notas Fiscais'
        ordering = ['-data_segmentacao', '-numero_nota']

    def __str__(self):
        return f'Log NF {self.numero_nota} — {self.cliente}'


class FolhaSalario(models.Model):
    """Tabela para armazenar os salários mensais das empresas para cálculo do Fator R"""
    MES_CHOICES = [
        (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
        (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
        (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
    ]
    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        verbose_name='Empresa',
    )
    ano = models.IntegerField(verbose_name='Ano')
    mes = models.IntegerField(verbose_name='Mês', choices=MES_CHOICES)
    total_salario = models.DecimalField(
        verbose_name='Total Salário (R$)',
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    class Meta:
        verbose_name = 'Folha de Salário'
        verbose_name_plural = 'Folhas de Salário'
        ordering = ['empresa', 'ano', 'mes']
        unique_together = [('empresa', 'ano', 'mes')]

    def __str__(self):
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        return f"{self.empresa.razao} - {meses[self.mes - 1]}/{self.ano} - R$ {self.total_salario}"


class ApuracaoPeriodo(models.Model):
    """Período de apuração fiscal (aberto/fechado). FK empresa referencia empresa.Empresa."""
    STATUS_CHOICES = [
        ('aberto', 'Aberto'),
        ('fechado', 'Fechado'),
    ]
    empresa = models.ForeignKey(
        'empresa.Empresa',
        on_delete=models.CASCADE,
        verbose_name='Empresa',
    )
    data_inicio = models.DateField(verbose_name='Data Início')
    data_fim = models.DateField(verbose_name='Data Fim')
    status = models.CharField(
        verbose_name='Status',
        max_length=10,
        choices=STATUS_CHOICES,
        default='aberto',
    )
    adicional_calculado = models.BooleanField(verbose_name='Adicional Calculado', default=False)
    valor_adicional = models.DecimalField(
        verbose_name='Valor Adicional',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    data_fechamento = models.DateTimeField(verbose_name='Data Fechamento', null=True, blank=True)
    usuario_fechamento = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Usuário Fechamento',
    )

    class Meta:
        verbose_name = 'Apuração de Período'
        verbose_name_plural = 'Apurações de Período'
        unique_together = [('empresa', 'data_inicio', 'data_fim')]
        ordering = ['empresa', 'data_inicio']

    def __str__(self):
        return f"Apuração {self.data_inicio} - {self.data_fim} ({self.empresa.razao})"

    def calcular_meses_periodo(self):
        from dateutil.relativedelta import relativedelta
        delta = relativedelta(self.data_fim, self.data_inicio)
        return delta.months + 1 + (delta.years * 12)

    def _total_bruto_periodo(self):
        from decimal import Decimal
        from django.db.models import Sum

        t = (
            NotaFiscalServico.objects.filter(
                empresa=self.empresa,
                data_emissao__gte=self.data_inicio,
                data_emissao__lte=self.data_fim,
            ).aggregate(s=Sum('valor_bruto'))['s']
            or Decimal('0')
        )
        return t

    def calcular_adicional_irpj(self):
        from decimal import Decimal

        total_faturamento_all = self._total_bruto_periodo()

        notas = NotaFiscalServico.objects.filter(
            empresa=self.empresa,
            data_emissao__gte=self.data_inicio,
            data_emissao__lte=self.data_fim,
            codigo_da_regra_do_imposto__isnull=False,
        ).select_related('codigo_da_regra_do_imposto')

        bases_por_regra = {}
        percentual_por_regra = {}
        total_faturamento_com_regra_pct = Decimal('0')

        for nota in notas:
            regra = nota.codigo_da_regra_do_imposto
            percentual = getattr(regra, 'percentual_calculo', 0) or 0
            if percentual > 0:
                percentual_decimal = Decimal(str(percentual))
                base = (nota.valor_bruto or Decimal('0')) * (percentual_decimal / Decimal('100'))
                rid = regra.id
                bases_por_regra[rid] = bases_por_regra.get(rid, Decimal('0')) + base
                percentual_por_regra[rid] = percentual_decimal
                total_faturamento_com_regra_pct += nota.valor_bruto or Decimal('0')

        meses = self.calcular_meses_periodo()
        limite_mensal = Decimal('20000')
        limite_periodo = limite_mensal * Decimal(str(meses))

        # Uma única regra com percentual: base = faturamento bruto total do período × %
        if len(bases_por_regra) == 1:
            rid = next(iter(bases_por_regra))
            pct = percentual_por_regra[rid]
            total_bases = total_faturamento_all * (pct / Decimal('100'))
        else:
            total_bases = sum(bases_por_regra.values())

        base_adicional = total_bases - limite_periodo
        valor_adicional = (base_adicional * Decimal('0.10')) if base_adicional > 0 else Decimal('0')

        if valor_adicional > 0:
            if len(bases_por_regra) == 1 and total_faturamento_all > 0:
                indice = valor_adicional / total_faturamento_all
                todas = NotaFiscalServico.objects.filter(
                    empresa=self.empresa,
                    data_emissao__gte=self.data_inicio,
                    data_emissao__lte=self.data_fim,
                )
                for nota in todas:
                    vb = nota.valor_bruto or Decimal('0')
                    nota.irpjadicional = vb * indice
                    nota.save(update_fields=['irpjadicional'])
            elif total_faturamento_com_regra_pct > 0:
                indice = valor_adicional / total_faturamento_com_regra_pct
                for nota in notas:
                    p = getattr(nota.codigo_da_regra_do_imposto, 'percentual_calculo', 0) or 0
                    if p > 0:
                        vb = nota.valor_bruto or Decimal('0')
                        nota.irpjadicional = vb * indice
                        nota.save(update_fields=['irpjadicional'])

        self.valor_adicional = valor_adicional
        self.adicional_calculado = True
        self.save(update_fields=['valor_adicional', 'adicional_calculado'])
        return float(valor_adicional), []

    def fechar_periodo(self, usuario):
        self.status = 'fechado'
        self.data_fechamento = timezone.now()
        self.usuario_fechamento = usuario
        self.save(update_fields=['status', 'data_fechamento', 'usuario_fechamento'])

    def reabrir_periodo(self):
        self.status = 'aberto'
        self.data_fechamento = None
        self.usuario_fechamento = None
        self.save(update_fields=['status', 'data_fechamento', 'usuario_fechamento'])

    def get_preview_adicional_irpj(self):
        """Retorna dados de preview do cálculo do adicional de IRPJ trimestral"""
        from django.db.models import Sum
        from decimal import Decimal

        total_faturamento = NotaFiscalServico.objects.filter(
            empresa=self.empresa,
            data_emissao__gte=self.data_inicio,
            data_emissao__lte=self.data_fim
        ).aggregate(total=Sum('valor_bruto'))['total'] or Decimal('0')

        notas_com_regras = NotaFiscalServico.objects.filter(
            empresa=self.empresa,
            data_emissao__gte=self.data_inicio,
            data_emissao__lte=self.data_fim,
            codigo_da_regra_do_imposto__isnull=False
        ).select_related('codigo_da_regra_do_imposto')

        meses = self.calcular_meses_periodo()
        regras_data = {}

        for nota in notas_com_regras:
            regra = nota.codigo_da_regra_do_imposto
            percentual = getattr(regra, 'percentual_calculo', 0) or 0
            percentual_decimal = Decimal(str(percentual))

            if percentual > 0:
                base = nota.valor_bruto * (percentual_decimal / Decimal('100'))
                if regra.id not in regras_data:
                    regras_data[regra.id] = {
                        'regra_nome': regra.DescricaoRegraImposto,
                        'percentual': percentual,
                        'faturamento_notas_esta_regra': Decimal('0'),
                        'base_calculada': Decimal('0')
                    }
                regras_data[regra.id]['faturamento_notas_esta_regra'] += nota.valor_bruto
                regras_data[regra.id]['base_calculada'] += base

        # Uma regra: base presumida sobre todo o faturamento bruto do período × %
        if len(regras_data) == 1:
            unica = next(iter(regras_data.values()))
            pct = Decimal(str(unica['percentual'] or 0))
            if pct > 0:
                unica['base_calculada'] = total_faturamento * (pct / Decimal('100'))

        limite_mensal = Decimal('20000')
        limite_periodo = limite_mensal * Decimal(str(meses))
        total_bases = sum(r['base_calculada'] for r in regras_data.values())
        base_adicional_total = total_bases - limite_periodo
        valor_adicional_total_projetado = base_adicional_total * Decimal('0.10') if base_adicional_total > 0 else Decimal('0')
        if total_faturamento > 0 and valor_adicional_total_projetado > 0:
            indice_projetado = float(valor_adicional_total_projetado / total_faturamento)
        else:
            indice_projetado = 0

        preview_data = {
            'meses_periodo': meses,
            'limite_mensal': float(limite_mensal),
            'limite_periodo': float(limite_periodo),
            'total_faturamento': float(total_faturamento),
            'regras': list(regras_data.values())
        }
        for regra in preview_data['regras']:
            base_adicional = regra['base_calculada'] - limite_periodo
            regra['base_adicional_projetada'] = float(base_adicional)
            regra['adicional_projetado'] = float(base_adicional * Decimal('0.10')) if base_adicional > 0 else 0
            regra['teria_calculo'] = base_adicional > 0
            regra['indice'] = indice_projetado
            # Coluna "Faturamento": mesmo total do período (todas as NF), alinhado ao resumo do modal
            regra['faturamento_notas_esta_regra'] = float(regra['faturamento_notas_esta_regra'])
            regra['total_faturamento'] = float(total_faturamento)
            regra['base_calculada'] = float(regra['base_calculada'])
        return preview_data

    def get_detalhes_calculo_adicional(self):
        """Retorna detalhes do cálculo do adicional realizado no mesmo formato do preview"""
        from django.db.models import Sum
        from decimal import Decimal

        total_faturamento = NotaFiscalServico.objects.filter(
            empresa=self.empresa,
            data_emissao__gte=self.data_inicio,
            data_emissao__lte=self.data_fim
        ).aggregate(total=Sum('valor_bruto'))['total'] or Decimal('0')

        notas_com_regras = NotaFiscalServico.objects.filter(
            empresa=self.empresa,
            data_emissao__gte=self.data_inicio,
            data_emissao__lte=self.data_fim,
            codigo_da_regra_do_imposto__isnull=False
        ).select_related('codigo_da_regra_do_imposto')

        meses = self.calcular_meses_periodo()
        regras_data = {}
        total_adicional_calculado = Decimal('0')

        for nota in notas_com_regras:
            regra = nota.codigo_da_regra_do_imposto
            percentual = getattr(regra, 'percentual_calculo', 0) or 0
            percentual_decimal = Decimal(str(percentual))
            adicional = nota.irpjadicional or Decimal('0')

            if percentual > 0:
                base = nota.valor_bruto * (percentual_decimal / Decimal('100'))
                if regra.id not in regras_data:
                    regras_data[regra.id] = {
                        'regra_nome': regra.DescricaoRegraImposto,
                        'percentual': percentual,
                        'faturamento_notas_esta_regra': Decimal('0'),
                        'base_calculada': Decimal('0'),
                        'base_adicional_calculada': Decimal('0'),
                        'adicional_calculado': Decimal('0')
                    }
                regras_data[regra.id]['faturamento_notas_esta_regra'] += nota.valor_bruto
                regras_data[regra.id]['base_calculada'] += base
                regras_data[regra.id]['adicional_calculado'] += adicional
                total_adicional_calculado += adicional

        if len(regras_data) == 1:
            unica = next(iter(regras_data.values()))
            pct = Decimal(str(unica['percentual'] or 0))
            if pct > 0:
                unica['base_calculada'] = total_faturamento * (pct / Decimal('100'))

        limite_mensal = Decimal('20000')
        limite_periodo = limite_mensal * Decimal(str(meses))
        if total_faturamento > 0 and total_adicional_calculado > 0:
            indice_geral = float(total_adicional_calculado / total_faturamento)
        else:
            indice_geral = 0

        detalhes_data = {
            'meses_periodo': meses,
            'limite_mensal': float(limite_mensal),
            'limite_periodo': float(limite_periodo),
            'total_faturamento': float(total_faturamento),
            'total_adicional_periodo': float(total_adicional_calculado),
            'regras': list(regras_data.values())
        }
        for regra in detalhes_data['regras']:
            base_adicional = regra['base_calculada'] - limite_periodo
            regra['base_adicional_calculada'] = float(base_adicional)
            regra['indice'] = indice_geral
            regra['faturamento_notas_esta_regra'] = float(regra['faturamento_notas_esta_regra'])
            regra['total_faturamento'] = float(total_faturamento)
            regra['base_calculada'] = float(regra['base_calculada'])
            regra['adicional_calculado'] = float(regra['adicional_calculado'])
        return detalhes_data


class AnexoSimplesNacional(models.Model):
    """Tabelas de anexos do Simples Nacional (faixas, alíquotas, percentuais)."""
    ANEXO_CHOICES = [
        ('I', 'Anexo I - Comércio'),
        ('II', 'Anexo II - Indústria'),
        ('III', 'Anexo III - Serviços'),
        ('IV', 'Anexo IV - Serviços'),
        ('V', 'Anexo V - Serviços'),
        ('VI', 'Anexo VI - Serviços'),
    ]
    anexo = models.CharField(verbose_name='Anexo', max_length=3, choices=ANEXO_CHOICES)
    faixa = models.CharField(verbose_name='Faixa', max_length=10)
    limite_inferior = models.DecimalField(verbose_name='Limite Inferior (R$)', max_digits=12, decimal_places=2, default=0)
    limite_superior = models.DecimalField(verbose_name='Limite Superior (R$)', max_digits=12, decimal_places=2, null=True, blank=True)
    aliquota = models.DecimalField(verbose_name='Alíquota (%)', max_digits=5, decimal_places=2)
    valor_deduzir = models.DecimalField(verbose_name='Valor a Deduzir (R$)', max_digits=10, decimal_places=2, default=0)
    ano_vigencia = models.IntegerField(verbose_name='Ano de Vigência', default=2024)
    percentual_irpj = models.DecimalField(verbose_name='IRPJ (%)', max_digits=5, decimal_places=2, default=0)
    percentual_csll = models.DecimalField(verbose_name='CSLL (%)', max_digits=5, decimal_places=2, default=0)
    percentual_cofins = models.DecimalField(verbose_name='COFINS (%)', max_digits=5, decimal_places=2, default=0)
    percentual_pis = models.DecimalField(verbose_name='PIS (%)', max_digits=5, decimal_places=2, default=0)
    percentual_cpp = models.DecimalField(verbose_name='CPP (%)', max_digits=5, decimal_places=2, default=0)
    percentual_iss = models.DecimalField(verbose_name='ISS (%)', max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Anexo Simples Nacional'
        verbose_name_plural = 'Anexos Simples Nacional'
        ordering = ['anexo', 'faixa']
        unique_together = [('anexo', 'faixa', 'ano_vigencia')]

    def __str__(self):
        return f"Anexo {self.anexo} - Faixa {self.faixa} ({self.ano_vigencia})"