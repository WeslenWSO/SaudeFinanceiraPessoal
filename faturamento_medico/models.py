from django.db import models
from django.utils import timezone
from empresa.models import Empresa
from decimal import Decimal
import os


def data_atual():
    """Retorna a data atual"""
    return timezone.now().date()


class FaturamentoMedico(models.Model):
    """Modelo para Faturamento Médico"""

    # Empresa
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')

    # Campos principais
    lote = models.CharField(verbose_name='Lote', max_length=50, blank=True, null=True)
    guia = models.CharField(verbose_name='Guia', max_length=50, blank=True, null=True)
    senha = models.CharField(verbose_name='Senha', max_length=50, blank=True, default='')
    carteirinha = models.CharField(verbose_name='Carteirinha', max_length=50, blank=True, null=True)
    nome = models.CharField(verbose_name='Nome', max_length=200, blank=True, null=True)
    nome_associado = models.CharField(
        verbose_name='Nome do Associado',
        max_length=200,
        blank=True,
        null=True,
    )
    codigo_servico = models.CharField(verbose_name='Código Serviço', max_length=20, blank=True, null=True)
    servico = models.CharField(verbose_name='Serviço', max_length=200, blank=True, null=True)

    # Datas
    data_autorizacao = models.DateField(verbose_name='Data da Autorização', blank=True, null=True)
    data = models.DateField(verbose_name='Data', default=data_atual)

    # Valores
    porte = models.CharField(verbose_name='Porte', max_length=20, blank=True, null=True)
    qt = models.IntegerField(verbose_name='QT', default=1)
    valor = models.DecimalField(verbose_name='Valor', max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(verbose_name='Total', max_digits=10, decimal_places=2, default=0)

    # Profissionais
    local = models.CharField(verbose_name='Local', max_length=200, blank=True, null=True)
    medico = models.CharField(verbose_name='Médico', max_length=200, blank=True, null=True)
    anestesista = models.CharField(verbose_name='Anestesista', max_length=200, blank=True, null=True)

    # Outros
    convenio = models.CharField(verbose_name='Convênio', max_length=100, blank=True, null=True)
    receber_por = models.CharField(verbose_name='Receber Por', max_length=100, blank=True, null=True)
    apartamento_enfermaria = models.CharField(
        verbose_name='Apartamento ou Enfermaria',
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('Apartamento', 'Apartamento'),
            ('Enfermaria', 'Enfermaria'),
        ]
    )
    urgencia = models.CharField(
        verbose_name='Urgência',
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('Sim', 'Sim'),
            ('Não', 'Não'),
        ]
    )
    observacao = models.TextField(verbose_name='Observação', blank=True, null=True)
    cpf = models.CharField(verbose_name='CPF', max_length=20, blank=True, null=True)
    horario = models.CharField(verbose_name='Horário', max_length=50, blank=True, null=True)
    horario_inicio = models.CharField(verbose_name='Horário de Início', max_length=20, blank=True, null=True)
    horario_fim = models.CharField(verbose_name='Horário de Fim', max_length=20, blank=True, null=True)
    prioridade = models.CharField(verbose_name='Prioridade', max_length=50, blank=True, null=True)
    status_agendamento = models.CharField(
        verbose_name='Status do Agendamento',
        max_length=50,
        blank=True,
        null=True,
    )
    motivo_cancelamento = models.CharField(
        verbose_name='Motivo Cancelamento/Desistência/Deleção',
        max_length=255,
        blank=True,
        null=True,
    )
    medico_solicitante = models.CharField(
        verbose_name='Médico Solicitante',
        max_length=200,
        blank=True,
        null=True,
    )
    tecnico = models.CharField(verbose_name='Técnico', max_length=200, blank=True, null=True)
    checkin_por = models.CharField(verbose_name='Check-in Por', max_length=200, blank=True, null=True)
    agendado_por = models.CharField(verbose_name='Agendado Por', max_length=200, blank=True, null=True)
    tag = models.CharField(verbose_name='Tag', max_length=100, blank=True, null=True)
    indicacao_clinica = models.TextField(verbose_name='Indicação Clínica', blank=True, null=True)
    descricao = models.TextField(verbose_name='Descrição', blank=True, null=True)
    guia_lancada = models.CharField(verbose_name='Protocolo', max_length=50, blank=True, default='')
    numero_guia_lancada = models.CharField(verbose_name='Número da Guia Lançada', max_length=50, blank=True, null=True)
    nota_fiscal = models.CharField(verbose_name='Nota Fiscal', max_length=50, blank=True, null=True)
    codigo_relatorio = models.CharField(verbose_name='Código Relatório', max_length=50, blank=True, null=True)
    medcloud_schedule_id = models.BigIntegerField(
        verbose_name='ID Agendamento MedCloud',
        blank=True,
        null=True,
        db_index=True,
    )
    link_laudo = models.URLField(verbose_name='Link do Laudo', max_length=500, blank=True, null=True)
    link_viewer = models.URLField(verbose_name='Link Viewer DICOM', max_length=500, blank=True, null=True)
    link_fastshare = models.URLField(verbose_name='Link FastShare', max_length=500, blank=True, null=True)
    laudo_expires_at = models.DateTimeField(verbose_name='Expiração do Link do Laudo', blank=True, null=True)
    agendado_via = models.CharField(verbose_name='Agendado Via', max_length=50, blank=True, null=True)
    data_fechamento = models.DateField(verbose_name='Data de Fechamento', blank=True, null=True)
    FATURAMENTO_STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aguardando_pagamento', 'Aguardando pagamento'),
        ('enviado', 'Enviado'),
        ('finalizado', 'Finalizado'),
    ]

    status = models.CharField(
        verbose_name='Status',
        max_length=25,
        choices=FATURAMENTO_STATUS_CHOICES,
        default='pendente'
    )
    codigo_fechamento = models.CharField(
        verbose_name='Código de Fechamento',
        max_length=20,
        blank=True,
        null=True,
        unique=True
    )
    percentual_imposto = models.DecimalField(
        verbose_name='Percentual de Imposto (%)',
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Percentual do imposto a ser aplicado'
    )
    percentual_comissao = models.DecimalField(
        verbose_name='Percentual de Comissão (%)',
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Percentual da comissão a ser aplicada'
    )
    valor_imposto = models.DecimalField(
        verbose_name='Valor do Imposto',
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Valor calculado do imposto'
    )
    valor_comissao = models.DecimalField(
        verbose_name='Valor da Comissão',
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Valor calculado da comissão'
    )

    # Timestamps
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Faturamento Médico'
        verbose_name_plural = 'Faturamentos Médicos'
        ordering = ['-data', '-data_criacao']

    def __str__(self):
        return f"{self.nome or 'Sem nome'} - {self.servico or 'Sem serviço'} - R$ {self.total}"

    def get_valor_liquido(self):
        """Calcula o valor líquido: Total - Imposto - Comissão"""
        return self.total - self.valor_imposto - self.valor_comissao

    def save(self, *args, **kwargs):
        """Calcula o total baseado nos itens de serviço"""
        super().save(*args, **kwargs)
        # Recalcula o total baseado nos itens
        self.atualizar_total()

    def atualizar_total(self):
        """Atualiza o total baseado na soma dos itens de serviço"""
        total_itens = self.itens_servico.aggregate(
            total=models.Sum('total')
        )['total'] or 0
        self.total = total_itens
        # Salva sem chamar save() novamente para evitar loop
        super().save(update_fields=['total'])


def documento_upload_path(instance, filename):
    """Função para definir o caminho de upload dos documentos"""
    return f'faturamento_medico/documentos/{instance.faturamento.id}/{filename}'


class DocumentoAnexado(models.Model):
    """Modelo para documentos anexados aos faturamentos médicos"""

    faturamento = models.ForeignKey(
        FaturamentoMedico,
        on_delete=models.CASCADE,
        related_name='documentos_anexados',
        verbose_name='Faturamento'
    )
    arquivo = models.FileField(
        upload_to=documento_upload_path,
        verbose_name='Arquivo',
        help_text='Selecione o arquivo a ser anexado'
    )
    nome = models.CharField(
        verbose_name='Nome do Documento',
        max_length=200,
        blank=True,
        help_text='Nome descritivo do documento (opcional)'
    )
    descricao = models.TextField(
        verbose_name='Descrição',
        blank=True,
        null=True,
        help_text='Descrição do documento (opcional)'
    )
    data_upload = models.DateTimeField(
        verbose_name='Data de Upload',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Documento Anexado'
        verbose_name_plural = 'Documentos Anexados'
        ordering = ['-data_upload']

    def __str__(self):
        nome_arquivo = self.nome or os.path.basename(self.arquivo.name)
        return f"{nome_arquivo} - {self.faturamento}"

    def get_file_size(self):
        """Retorna o tamanho do arquivo em formato legível"""
        try:
            size = self.arquivo.size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        except:
            return "Tamanho desconhecido"

    def get_file_extension(self):
        """Retorna a extensão do arquivo"""
        try:
            return os.path.splitext(self.arquivo.name)[1].lower()
        except:
            return ""


class ServicoDisponivel(models.Model):
    """Modelo para serviços disponíveis para seleção nos itens"""

    codigo = models.CharField(verbose_name='Código do Serviço', max_length=20, unique=True)
    descricao = models.CharField(verbose_name='Descrição do Serviço', max_length=200)
    porte = models.CharField(verbose_name='Porte ANESTÉSICO', max_length=50, blank=True, null=True)
    valor_base = models.DecimalField(verbose_name='Valor Base', max_digits=10, decimal_places=2, default=0)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    # Campos para categorização
    categoria = models.CharField(verbose_name='Categoria', max_length=100, blank=True, null=True)
    subcategoria = models.CharField(verbose_name='Subcategoria', max_length=100, blank=True, null=True)

    # Timestamps
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Serviço Disponível'
        verbose_name_plural = 'Serviços Disponíveis'
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"

    def get_valor_formatado(self):
        """Retorna o valor formatado para exibição"""
        return f"R$ {self.valor_base:.2f}"


class ItemServico(models.Model):
    """Modelo para itens de serviço dentro de uma guia de faturamento"""

    faturamento = models.ForeignKey(
        FaturamentoMedico,
        on_delete=models.CASCADE,
        related_name='itens_servico',
        verbose_name='Faturamento'
    )
    codigo_servico = models.CharField(
        verbose_name='Código Serviço',
        max_length=20,
        blank=True,
        null=True
    )
    servico = models.CharField(
        verbose_name='Serviço',
        max_length=200,
        blank=True,
        null=True
    )
    porte = models.CharField(
        verbose_name='Porte',
        max_length=20,
        blank=True,
        null=True
    )
    qt = models.IntegerField(
        verbose_name='QT',
        default=1
    )
    valor = models.DecimalField(
        verbose_name='Valor',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    percentual = models.DecimalField(
        verbose_name='Percentual',
        max_digits=5,
        decimal_places=2,
        default=1.00,
        help_text='Percentual a ser aplicado no cálculo (ex: 0.50 para 50%)'
    )
    total = models.DecimalField(
        verbose_name='Total',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    modalidade = models.CharField(
        verbose_name='Modalidade',
        max_length=20,
        blank=True,
        null=True
    )
    com_contraste = models.BooleanField(
        verbose_name='Com Contraste',
        default=False
    )
    conferido = models.BooleanField(
        verbose_name='Conferência',
        default=False
    )
    STATUS_CONFERENCIA_CHOICES = [
        ('PENDENTE', 'PENDENTE'),
        ('CONFERIDO', 'CONFERIDO'),
        ('LOTE OK', 'LOTE OK'),
        ('FALTA DE GUIA', 'FALTA DE GUIA'),
        ('FALTA DE VALOR NA TABELA', 'FALTA DE VALOR NA TABELA'),
        ('FALTA TABELA DE CONTRASTE', 'FALTA TABELA DE CONTRASTE'),
        ('OUTROS', 'OUTROS'),
    ]
    STATUS_CONFERENCIA_CSS = {
        'CONFERIDO': 'success',
        'LOTE OK': 'lote-ok',
        'FALTA DE GUIA': 'warning',
        'FALTA DE VALOR NA TABELA': 'danger',
        'FALTA TABELA DE CONTRASTE': 'contraste',
        'OUTROS': 'info',
        'PENDENTE': 'secondary',
    }
    status_conferencia = models.CharField(
        verbose_name='Status Conferência',
        max_length=40,
        choices=STATUS_CONFERENCIA_CHOICES,
        default='PENDENTE',
        blank=True,
    )
    valor_glosa = models.DecimalField(
        verbose_name='Valor da Glosa',
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    data_recorrencia = models.DateField(
        verbose_name='Data da Recorrência',
        null=True,
        blank=True,
    )
    data_criacao = models.DateTimeField(
        verbose_name='Data de Criação',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Item de Serviço'
        verbose_name_plural = 'Itens de Serviço'
        ordering = ['data_criacao']

    def __str__(self):
        return f"{self.servico or 'Serviço'} - {self.qt}x R$ {self.valor}"

    def save(self, *args, **kwargs):
        """Calcula o total automaticamente"""
        from decimal import Decimal
        self.total = Decimal(self.qt) * Decimal(str(self.valor)) * Decimal(str(self.percentual))
        if self.conferido and (self.status_conferencia or '').strip() != 'LOTE OK':
            self.status_conferencia = 'CONFERIDO'
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = list(set(update_fields) | {'status_conferencia', 'total'})
        super().save(*args, **kwargs)

    def status_conferencia_badge(self, tem_preco_tabela=None):
        """
        Retorna (label, css_class) do status de conferência persistido.
        Se ainda estiver PENDENTE e houver sugestão automática, usa a sugestão só para exibição
        quando o status armazenado for vazio.
        """
        status = (self.status_conferencia or '').strip() or 'PENDENTE'
        if self.conferido and status != 'LOTE OK':
            status = 'CONFERIDO'
        css = self.STATUS_CONFERENCIA_CSS.get(status, 'secondary')
        return (status, css)

    def sugerir_status_conferencia(self, tem_preco_tabela=None):
        """Sugestão automática (usada no backfill / importação)."""
        if self.conferido:
            return 'CONFERIDO'
        valor = self.total if self.total is not None else self.valor
        if tem_preco_tabela is False or (tem_preco_tabela is None and (valor is None or valor == 0)):
            return 'FALTA DE VALOR NA TABELA'
        guia = ''
        if getattr(self, 'faturamento_id', None):
            guia = (self.faturamento.guia or '').strip()
        if not guia:
            return 'FALTA DE GUIA'
        return 'PENDENTE'

    def aplicar_status_conferencia(self, status):
        """Define status manualmente e sincroniza o checkbox conferido."""
        status = (status or '').strip()
        validos = {c[0] for c in self.STATUS_CONFERENCIA_CHOICES}
        if status not in validos:
            status = 'PENDENTE'
        self.status_conferencia = status
        self.conferido = status in ('CONFERIDO', 'LOTE OK')
        self.save(update_fields=['status_conferencia', 'conferido'])
        return self.status_conferencia_badge()


class Lote(models.Model):
    """Modelo para Lote de Faturamento Médico"""

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    convenio = models.CharField(verbose_name='Convênio', max_length=100, blank=True, null=True)
    data_lote = models.DateField(verbose_name='Data do Lote', default=timezone.now)
    total_lote = models.DecimalField(verbose_name='Total do Lote', max_digits=15, decimal_places=2, default=0)
    baixado = models.BooleanField(
        verbose_name='Lote baixado',
        default=False,
        help_text='Lote recebido e baixado — oculto na impressão e ao adicionar faturamentos.',
    )

    # Timestamps
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Lote'
        verbose_name_plural = 'Lotes'
        ordering = ['-data_lote', '-data_criacao']

    def __str__(self):
        return f"Lote {self.id} - {self.convenio} - R$ {self.total_lote}"

    def aberto_para_adicionar(self) -> bool:
        """False se o lote foi baixado ou todos os faturamentos já estão finalizados."""
        if self.baixado:
            return False
        fats = FaturamentoMedico.objects.filter(empresa_id=self.empresa_id, lote=str(self.id))
        if not fats.exists():
            return True
        return fats.exclude(status='finalizado').exists()

    def save(self, *args, **kwargs):
        """Calcula o total do lote baseado nos faturamentos associados"""
        super().save(*args, **kwargs)
        self.atualizar_total()

    def atualizar_total(self):
        """Atualiza o total baseado na soma dos faturamentos do lote"""
        from django.db.models import Sum
        total_faturamentos = FaturamentoMedico.objects.filter(lote=str(self.id)).aggregate(
            total=Sum('total')
        )['total'] or 0
        self.total_lote = total_faturamentos
        # Salva sem chamar save() novamente para evitar loop
        super().save(update_fields=['total_lote'])

    def sincronizar_extrato_pagamento(
        self,
        *,
        lote_convenio: str = '',
        protocolo: str | None = None,
    ):
        """Cria ou atualiza linha na tabela Extrato de Pagamento ao gerar/adicionar lote."""
        from django.db.models import Count
        from django.db.models.functions import TruncMonth

        faturamentos = FaturamentoMedico.objects.filter(
            empresa_id=self.empresa_id,
            lote=str(self.id),
        )
        if not faturamentos.exists():
            ExtratoPagamentoConvenio.objects.filter(lote_faturamento=self).delete()
            return None

        qt_guias = (
            faturamentos.exclude(guia__isnull=True)
            .exclude(guia='')
            .values('guia')
            .distinct()
            .count()
        )
        if not qt_guias:
            qt_guias = faturamentos.count()

        mes_dominante = (
            faturamentos.annotate(mes=TruncMonth('data'))
            .values('mes')
            .annotate(qtd=Count('id'))
            .order_by('-qtd', '-mes')
            .first()
        )
        if mes_dominante and mes_dominante.get('mes'):
            ref = mes_dominante['mes']
            competencia = f'{ref.month:02d}/{ref.year}'
        else:
            ref = self.data_lote or timezone.now().date()
            competencia = f'{ref.month:02d}/{ref.year}'

        convenio = (self.convenio or '').strip()
        if protocolo is None:
            protocolo_val = (
                faturamentos.exclude(guia_lancada__isnull=True)
                .exclude(guia_lancada='')
                .values_list('guia_lancada', flat=True)
                .first()
                or ''
            )
        else:
            protocolo_val = (protocolo or '').strip()
        lote_conv = (lote_convenio or '').strip()
        if not lote_conv:
            lote_conv = str(self.id)

        self.atualizar_total()
        valor = self.total_lote or Decimal('0')

        existente = ExtratoPagamentoConvenio.objects.filter(lote_faturamento=self).first()
        defaults = {
            'empresa_id': self.empresa_id,
            'competencia': competencia,
            'convenio': convenio,
            'data_lote': self.data_lote,
            'lote': lote_conv,
            'protocolo': protocolo_val,
            'qt_guias': qt_guias,
            'valor': valor,
            'banco': existente.banco if existente else '',
            'observacao': (
                existente.observacao if existente and existente.observacao
                else 'Gerado automaticamente ao formar lote de faturamento.'
            ),
        }
        if not existente or not existente.protocolo:
            defaults.update({
                'valor_processado': Decimal('0'),
                'valor_glosado': Decimal('0'),
                'valor_liberado': Decimal('0'),
                'retencoes': Decimal('0'),
                'liquido': Decimal('0'),
                'valor_recebido': Decimal('0'),
            })

        extrato, _created = ExtratoPagamentoConvenio.objects.update_or_create(
            lote_faturamento=self,
            defaults=defaults,
        )
        return extrato

    def recalcular_glosa_extrato(self):
        """Soma glosas dos procedimentos do lote e atualiza o extrato de pagamento."""
        from django.db.models import Sum

        total_glosa = ItemServico.objects.filter(
            faturamento__empresa_id=self.empresa_id,
            faturamento__lote=str(self.id),
        ).aggregate(total=Sum('valor_glosa'))['total'] or Decimal('0')

        extrato = ExtratoPagamentoConvenio.objects.filter(lote_faturamento=self).first()
        if not extrato:
            extrato = self.sincronizar_extrato_pagamento()
        if extrato:
            extrato.valor_glosado = total_glosa
            extrato.save(update_fields=['valor_glosado', 'data_atualizacao'])
        return extrato


class ExtratoPagamentoConvenio(models.Model):
    """Linha importada do Demonstrativo de Pagamento TISS (convênio)."""

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    lote_faturamento = models.ForeignKey(
        Lote,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='linhas_extrato_pagamento',
        verbose_name='Lote de faturamento',
    )
    competencia = models.CharField(verbose_name='Competência', max_length=7, blank=True, default='')
    convenio = models.CharField(verbose_name='Convênio', max_length=100, blank=True, default='')
    data_lote = models.DateField(verbose_name='Data do Lote', null=True, blank=True)
    lote = models.CharField(verbose_name='Lote', max_length=50, blank=True, default='')
    protocolo = models.CharField(verbose_name='Protocolo', max_length=50, blank=True, default='')
    qt_guias = models.PositiveIntegerField(verbose_name='Qt de Guia', null=True, blank=True)
    valor = models.DecimalField(verbose_name='Valor', max_digits=12, decimal_places=2, default=0)
    valor_processado = models.DecimalField(
        verbose_name='Valor Processado', max_digits=12, decimal_places=2, default=0, blank=True
    )
    valor_glosado = models.DecimalField(verbose_name='Valor Glosado', max_digits=12, decimal_places=2, default=0)
    valor_liberado = models.DecimalField(verbose_name='Valor Liberado', max_digits=12, decimal_places=2, default=0)
    observacao = models.TextField(verbose_name='Observação', blank=True, default='')
    nota = models.CharField(verbose_name='Nota', max_length=50, blank=True, default='')
    valor_nota = models.DecimalField(
        verbose_name='Valor da Nota', max_digits=12, decimal_places=2, null=True, blank=True
    )
    retencoes = models.DecimalField(verbose_name='Retenções', max_digits=12, decimal_places=2, default=0)
    liquido = models.DecimalField(verbose_name='Líquido', max_digits=12, decimal_places=2, default=0)
    data_previsao = models.DateField(verbose_name='Data de Previsão', null=True, blank=True)
    data_recebimento = models.DateField(verbose_name='Data de Recebimento', null=True, blank=True)
    valor_recebido = models.DecimalField(verbose_name='Valor Recebido', max_digits=12, decimal_places=2, default=0)
    banco = models.CharField(verbose_name='Banco', max_length=100, blank=True, default='')
    numero_demonstrativo = models.CharField(
        verbose_name='Nº Demonstrativo', max_length=50, blank=True, default=''
    )
    nome_arquivo = models.CharField(verbose_name='Arquivo origem', max_length=255, blank=True, default='')
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Extrato de Pagamento — Convênio'
        verbose_name_plural = 'Extratos de Pagamento — Convênio'
        ordering = ['-data_recebimento', '-competencia', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['lote_faturamento'],
                condition=models.Q(lote_faturamento__isnull=False),
                name='uniq_extrato_por_lote_faturamento',
            ),
            models.UniqueConstraint(
                fields=[
                    'empresa', 'competencia', 'protocolo', 'lote',
                    'data_recebimento', 'valor', 'valor_liberado',
                ],
                condition=models.Q(lote_faturamento__isnull=True),
                name='uniq_extrato_pagamento_convenio',
            ),
        ]

    def __str__(self):
        return f'{self.convenio} — {self.competencia} — lote {self.lote} — R$ {self.valor_recebido}'

    @property
    def baixado(self) -> bool:
        return self.data_recebimento is not None and (self.valor_recebido or 0) > 0

    def sincronizar_baixado_lote(self):
        """Marca lote e faturamentos conforme recebimento baixado no extrato."""
        lote = self.lote_faturamento
        if not lote:
            return
        baixado = self.baixado
        if lote.baixado != baixado:
            lote.baixado = baixado
            lote.save(update_fields=['baixado', 'data_atualizacao'])
        self.sincronizar_status_faturamentos_lote()

    def sincronizar_status_faturamentos_lote(self):
        """Ao receber extrato, finaliza faturamentos do lote; estorno volta a aguardando pagamento."""
        lote = self.lote_faturamento
        if not lote:
            return
        qs = FaturamentoMedico.objects.filter(
            empresa_id=self.empresa_id,
            lote=str(lote.id),
        )
        if self.baixado:
            atualizar = qs.filter(status__in=['aguardando_pagamento', 'enviado', 'pendente'])
            if self.data_recebimento:
                atualizar.update(status='finalizado', data_fechamento=self.data_recebimento)
            else:
                atualizar.update(status='finalizado')
        else:
            qs.filter(
                status='finalizado',
                codigo_fechamento__isnull=True,
            ).update(status='aguardando_pagamento', data_fechamento=None)


class MedcloudConfig(models.Model):
    """Credenciais MedCloud RIS/HIS por empresa."""

    empresa = models.OneToOneField(
        Empresa,
        on_delete=models.CASCADE,
        related_name='medcloud_config',
        verbose_name='Empresa',
    )
    ativo = models.BooleanField(verbose_name='Integração ativa', default=True)
    ris_base_url = models.URLField(
        verbose_name='URL base RIS',
        max_length=255,
        default='https://api.ris.medcloud.co',
    )
    ris_username = models.CharField(verbose_name='Usuário RIS', max_length=100, blank=True, default='')
    ris_password_cifrada = models.TextField(verbose_name='Senha RIS (cifrada)', blank=True, default='')
    ris_clinic_id = models.PositiveIntegerField(verbose_name='ID da clínica (clinicIdToAccess)', default=0)
    ris_lista_agendas_path = models.CharField(
        verbose_name='Path listagem de agendas',
        max_length=255,
        default='/schedules',
        help_text='GET com query startDate, endDate, status, partnerId. Confirme com a MedCloud.',
    )
    his_base_url = models.URLField(
        verbose_name='URL base HIS',
        max_length=255,
        default='https://his.medcloud.co/v1/his',
    )
    his_api_key_cifrada = models.TextField(verbose_name='API Key HIS (cifrada)', blank=True, default='')

    class Meta:
        verbose_name = 'Configuração MedCloud'
        verbose_name_plural = 'Configurações MedCloud'

    def __str__(self):
        return f'MedCloud — {self.empresa}'


class MedcloudConvenioParceiro(models.Model):
    """Mapeia convênio local → partnerId MedCloud e regras de laudo."""

    config = models.ForeignKey(
        MedcloudConfig,
        on_delete=models.CASCADE,
        related_name='convenios',
        verbose_name='Configuração MedCloud',
    )
    convenio_nome = models.CharField(
        verbose_name='Nome do convênio (faturamento)',
        max_length=100,
        help_text='Deve coincidir com o campo convênio do faturamento médico.',
    )
    partner_id = models.PositiveIntegerField(verbose_name='Partner ID MedCloud')
    exige_laudo = models.BooleanField(
        verbose_name='Exige laudo liberado',
        default=True,
        help_text='Convênios marcados entram na busca diária de links de laudo.',
    )

    class Meta:
        verbose_name = 'Convênio MedCloud'
        verbose_name_plural = 'Convênios MedCloud'
        ordering = ['convenio_nome']
        unique_together = [['config', 'convenio_nome']]

    def __str__(self):
        return f'{self.convenio_nome} (partner {self.partner_id})'


class MetaModalidadeSolicitante(models.Model):
    """Meta de quantidade de exames por modalidade para um solicitante."""

    MODALIDADE_CHOICES = (
        ('MR', 'Ressonância'),
        ('US', 'Ultrassonografia'),
        ('CR', 'Raio X'),
        ('CT', 'Tomografia'),
        ('MG', 'Mamografia'),
        ('EG', 'EEG'),
    )

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='metas_solicitante_modalidade',
        verbose_name='Empresa',
    )
    solicitante = models.CharField(verbose_name='Solicitante', max_length=200)
    modalidade = models.CharField(
        verbose_name='Modalidade',
        max_length=10,
        choices=MODALIDADE_CHOICES,
    )
    meta = models.PositiveIntegerField(verbose_name='Meta', default=0)

    class Meta:
        verbose_name = 'Meta por modalidade (solicitante)'
        verbose_name_plural = 'Metas por modalidade (solicitante)'
        ordering = ['solicitante', 'modalidade']
        unique_together = [['empresa', 'solicitante', 'modalidade']]

    def __str__(self):
        return f'{self.solicitante} — {self.get_modalidade_display()}: {self.meta}/mês'


class ApelidoSolicitante(models.Model):
    """Apelido único para um ou mais nomes (grafias) do médico solicitante no RIS."""

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='apelidos_solicitante',
        verbose_name='Empresa',
    )
    apelido = models.CharField(verbose_name='Apelido', max_length=200)
    grafia = models.CharField(
        verbose_name='Grafia no RIS',
        max_length=200,
        help_text='Nome exato do campo médico solicitante no faturamento.',
    )

    class Meta:
        verbose_name = 'Apelido de solicitante'
        verbose_name_plural = 'Apelidos de solicitante'
        ordering = ['apelido', 'grafia']
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'grafia'],
                name='uniq_apelido_solicitante_empresa_grafia',
            ),
        ]

    def __str__(self):
        return f'{self.apelido} ← {self.grafia}'
