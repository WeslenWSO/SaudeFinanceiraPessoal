from django.db import models
from django.utils import timezone
from empresa.models import Empresa
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
    guia_lancada = models.BigIntegerField(verbose_name='Guia Lançada', default=0, blank=True, null=True)
    numero_guia_lancada = models.CharField(verbose_name='Número da Guia Lançada', max_length=50, blank=True, null=True)
    nota_fiscal = models.CharField(verbose_name='Nota Fiscal', max_length=50, blank=True, null=True)
    codigo_relatorio = models.CharField(verbose_name='Código Relatório', max_length=50, blank=True, null=True)
    agendado_via = models.CharField(verbose_name='Agendado Via', max_length=50, blank=True, null=True)
    data_fechamento = models.DateField(verbose_name='Data de Fechamento', blank=True, null=True)
    status = models.CharField(
        verbose_name='Status',
        max_length=20,
        choices=[
            ('pendente', 'Pendente'),
            ('enviado', 'Enviado'),
            ('finalizado', 'Finalizado'),
        ],
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
        ('FALTA DE GUIA', 'FALTA DE GUIA'),
        ('FALTA DE VALOR NA TABELA', 'FALTA DE VALOR NA TABELA'),
        ('OUTROS', 'OUTROS'),
    ]
    STATUS_CONFERENCIA_CSS = {
        'CONFERIDO': 'success',
        'FALTA DE GUIA': 'warning',
        'FALTA DE VALOR NA TABELA': 'danger',
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
        if self.conferido:
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
        if self.conferido:
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
        self.conferido = (status == 'CONFERIDO')
        self.save(update_fields=['status_conferencia', 'conferido'])
        return self.status_conferencia_badge()


class Lote(models.Model):
    """Modelo para Lote de Faturamento Médico"""

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    convenio = models.CharField(verbose_name='Convênio', max_length=100, blank=True, null=True)
    data_lote = models.DateField(verbose_name='Data do Lote', default=timezone.now)
    total_lote = models.DecimalField(verbose_name='Total do Lote', max_digits=15, decimal_places=2, default=0)

    # Timestamps
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Lote'
        verbose_name_plural = 'Lotes'
        ordering = ['-data_lote', '-data_criacao']

    def __str__(self):
        return f"Lote {self.id} - {self.convenio} - R$ {self.total_lote}"

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
