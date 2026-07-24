from decimal import Decimal

from django.db import models
from django.contrib.auth import get_user_model
from empresa.models import Empresa
import uuid


class Banco(models.Model):
    nome = models.CharField(max_length=120)
    codigo = models.CharField(max_length=10, blank=True, null=True)  # Código do banco (ex: 001, 237)
    logo = models.ImageField(blank=True, upload_to='logobanco/', null=True, verbose_name='Logo')

    def __str__(self):
        return self.nome

class ContaBancaria(models.Model):
    STATUS_CHOICES = [
        ('A', 'Ativa'),
        ('I', 'Inativa'),
    ]

    TIPO_CHOICES = [
        ('CAIXA', 'Caixa'),
        ('CONTA_CORRENTE', 'Conta Corrente'),
        ('POUPANCA', 'Poupança'),
        ('INVESTIMENTO', 'Investimento'),
        ('EMPRESTIMO', 'Empréstimo'),
        ('FATURA_CARTAO', 'Fatura de Cartão'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="contas")
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)
    agencia = models.CharField(max_length=20, blank=True, null=True)
    conta = models.CharField(max_length=30, blank=True, null=True)
    conta_contabil = models.CharField(max_length=20, blank=True, null=True, verbose_name='Conta Contábil')
    descricao = models.CharField(max_length=200, blank=True, null=True)
    saldo_inicial = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor de Saldo Inicial',
    )
    data_inicial_saldo = models.DateField(
        blank=True,
        null=True,
        verbose_name='Data Inicial do Saldo',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='CONTA_CORRENTE', verbose_name='Tipo')
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='A', verbose_name='Status')

    # API Sicoob (extrato automático): número usado no parâmetro numeroContaCorrente (vide portal desenvolvedor).
    sicoob_numero_conta_corrente_api = models.CharField(
        max_length=32,
        blank=True,
        default='',
        verbose_name='Sicoob — Nº conta API (extrato)',
        help_text='Somente dígitos, conforme exibido no app do desenvolvedor Sicoob para consulta de extrato.',
    )

    class Meta:
        unique_together = ("empresa", "banco", "agencia", "conta")

    def __str__(self):
        base = f"{self.banco} {self.descricao} - {self.agencia}/{self.conta}".strip()
        return f"{self.get_tipo_display()} - {base}"

class Conciliacao(models.Model):
    """Agrupador lógico para marcação de conciliado."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    observacao = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Conciliacao {self.id}"

class ExtratoArquivo(models.Model):
    TIPO_OFX = "OFX"
    TIPO_PDF = "PDF"
    TIPOS = [(TIPO_OFX, "OFX"), (TIPO_PDF, "PDF")]

    conta = models.ForeignKey(ContaBancaria, on_delete=models.CASCADE, related_name="arquivos")
    tipo = models.CharField(max_length=3, choices=TIPOS)
    arquivo = models.FileField(upload_to="extratos/")
    periodo_inicio = models.DateField(blank=True, null=True)
    periodo_fim = models.DateField(blank=True, null=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.conta} [{self.tipo}]"

class Lancamento(models.Model):
    """Linhas do extrato – inclui campos para conciliação."""
    STATUS_IMPORTACAO_CHOICES = [
        ('P', 'Pendente (prévia)'),
        ('I', 'Importado'),
        ('D', 'Duplicado'),
        ('X', 'Ignorado'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="lancamentos")
    conta = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name="lancamentos")
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)

    fitid = models.CharField(max_length=60, blank=True, null=True)          # FITID único do lançamento
    data = models.DateField()
    documento = models.CharField(max_length=60, blank=True, null=True)     # ex: cheque, NSU
    historico = models.CharField(max_length=255)                            # descrição/memo
    valor = models.DecimalField(max_digits=14, decimal_places=2)            # (+/-)
    saldo = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)  # saldo após o lançamento
    conciliado = models.BooleanField(default=False)
    idconciliacao = models.ForeignKey(Conciliacao, on_delete=models.SET_NULL, null=True, blank=True)
    origem = models.CharField(max_length=20, default="MANUAL")              # MANUAL/OFX/PDF
    hash_unico = models.CharField(max_length=64, db_index=True)             # para evitar duplicidade

    # Prévia/importação: vincula ao arquivo e indica status (P=prévia, I=importado, D=duplicado, X=ignorado)
    extrato_arquivo = models.ForeignKey(
        ExtratoArquivo, null=True, blank=True, on_delete=models.SET_NULL, related_name="lancamentos_importados"
    )
    status_importacao = models.CharField(
        max_length=1, choices=STATUS_IMPORTACAO_CHOICES, default='I', db_index=True
    )

    # Referência para o lançamento original em caso de transferência
    lancamento_origem_transferencia = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='lancamentos_destino_transferencia')

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["empresa", "conta", "data"]),
            models.Index(fields=["conciliado"]),
            models.Index(fields=["hash_unico"]),
            models.Index(fields=["fitid"]),
        ]
        constraints = [
            # Evita duplicar mesma linha do extrato baseado no FITID
            models.UniqueConstraint(fields=["conta", "fitid"], name="uniq_lancamento_fitid"),
            # Evita duplicar mesma linha do extrato baseado nos campos básicos
            models.UniqueConstraint(fields=["conta", "data", "documento", "valor", "historico"], name="uniq_lancamento_basico"),
        ]

    def tem_relatorios_cartao(self):
        """
        Verifica se o lançamento tem relatórios de máquina de cartão relacionados
        """
        from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

        # Verificar se há relatórios com identificacao_extrato contendo fitid
        if self.fitid:
            if RelatorioRecebiveisMaquinaCartao.objects.filter(
                empresa=self.empresa,
                conciliado=True,
                identificacao_extrato__icontains=str(self.fitid)
            ).exists():
                return True

        # Verificar através de movimentos do extrato
        movimentos = self.extrato_movimentos.filter(empresa=self.empresa, conta_receber__isnull=False)
        for movimento in movimentos:
            if movimento.conta_receber and RelatorioRecebiveisMaquinaCartao.objects.filter(
                empresa=self.empresa,
                conta_a_receber=movimento.conta_receber
            ).exists():
                return True

        return False

    def __str__(self):
        sinal = "+" if self.valor >= 0 else "-"
        fitid_info = f"[{self.fitid}]" if self.fitid else ""
        return f"{self.data} {fitid_info} {sinal}{abs(self.valor)} {self.historico[:40]}"


class ExtratoMovimento(models.Model):
    """Movimentos de contas a receber e contas a pagar"""

    SITUACAO_CHOICES = [
        ('recebido', 'Recebido'),
        ('pago', 'Pago'),
        ('estornado', 'Estornado'),
        ('cancelado', 'Cancelado'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="extrato_movimentos")
    data_baixa = models.DateField(verbose_name='Data da Baixa')
    descricao = models.CharField(max_length=255, verbose_name='Descrição')
    situacao = models.CharField(max_length=20, choices=SITUACAO_CHOICES, default='recebido', verbose_name='Situação')
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor Pago/Recebido')
    saldo = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Saldo', null=True, blank=True)

    # Relacionamentos opcionais
    conta_receber = models.ForeignKey('contasareceber.ContaAReceber', on_delete=models.SET_NULL, null=True, blank=True, related_name='extrato_movimentos')
    baixa_receber = models.ForeignKey('contasareceber.BaixaContaAReceber', on_delete=models.SET_NULL, null=True, blank=True, related_name='extrato_movimentos')
    conta_pagar = models.ForeignKey('contasapagar.ContasaPagar', on_delete=models.SET_NULL, null=True, blank=True, related_name='extrato_movimentos')

    # Lançamento do extrato bancário conciliado
    lancamento = models.ForeignKey('Lancamento', on_delete=models.SET_NULL, null=True, blank=True, related_name='extrato_movimentos')

    # Conta bancária onde foi feito o movimento
    conta_banco = models.ForeignKey('extrato.ContaBancaria', on_delete=models.SET_NULL, null=True, blank=True, related_name='extrato_movimentos')

    # Categoria do movimento
    categoria = models.ForeignKey('categoria.Categoria', on_delete=models.SET_NULL, null=True, blank=True, related_name='extrato_movimentos')

    # Timestamps
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Movimento do Extrato'
        verbose_name_plural = 'Movimentos do Extrato'
        ordering = ['-data_baixa', '-criado_em']
        indexes = [
            models.Index(fields=['empresa', 'data_baixa']),
            models.Index(fields=['situacao']),
            models.Index(fields=['conta_receber']),
            models.Index(fields=['conta_pagar']),
        ]

    def __str__(self):
        tipo = "Recebimento" if self.valor > 0 else "Pagamento"
        return f"{self.data_baixa} - {tipo} R$ {abs(self.valor)} - {self.descricao[:50]}"

    def save(self, *args, **kwargs):
        """Atualiza o saldo baseado nos movimentos anteriores e define data_baixa se houver lancamento"""
        # Se houver lancamento vinculado, definir data_baixa igual à data do lancamento
        if self.lancamento and self.lancamento.data:
            self.data_baixa = self.lancamento.data

        if not self.pk:  # Novo registro
            # Calcula o saldo baseado no último movimento da empresa
            ultimo_movimento = ExtratoMovimento.objects.filter(empresa=self.empresa).order_by('-data_baixa', '-criado_em').first()
            if ultimo_movimento and ultimo_movimento.saldo is not None:
                self.saldo = ultimo_movimento.saldo + self.valor
            else:
                self.saldo = self.valor
        super().save(*args, **kwargs)
