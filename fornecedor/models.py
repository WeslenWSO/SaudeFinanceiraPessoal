from django.db import models
from empresa.models import Empresa

from fornecedor.cnpj_utils import limpar_cnpj, limpar_cep, limpar_telefone_br

# Create your models here.
class Fornecedor(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    razao = models.CharField(verbose_name='Razão social', max_length=200)
    codigo_externo = models.CharField(
        verbose_name='Código externo',
        max_length=50,
        blank=True,
        default='',
        help_text='Usado na pasta ao salvar cópia do XML da NFSe (tomador): código-razão do prestador.',
    )
    cnpj = models.CharField(
        verbose_name='CNPJ / CPF',
        max_length=20,
        help_text='Somente números: CNPJ com 14 dígitos ou CPF com 11 dígitos (pessoa física).',
    )
    telefone = models.CharField(verbose_name='Telefone', max_length=20, blank=True, default='')

    nome_fantasia = models.CharField(verbose_name='Nome fantasia', max_length=200, blank=True, default='')
    atividades_cnae = models.TextField(verbose_name='Atividades (CNAE)', blank=True, default='')
    natureza_juridica = models.CharField(verbose_name='Natureza jurídica', max_length=200, blank=True, default='')
    porte = models.CharField(verbose_name='Porte', max_length=100, blank=True, default='')
    data_abertura = models.DateField(verbose_name='Data de abertura', null=True, blank=True)
    situacao_cadastral = models.CharField(verbose_name='Situação cadastral', max_length=100, blank=True, default='')
    data_situacao_cadastral = models.DateField(verbose_name='Data da situação cadastral', null=True, blank=True)
    cidade_uf = models.CharField(verbose_name='Cidade — UF', max_length=200, blank=True, default='')
    cep = models.CharField(verbose_name='CEP', max_length=15, blank=True, default='')
    logradouro = models.CharField(verbose_name='Logradouro', max_length=200, blank=True, default='')
    numero = models.CharField(verbose_name='Número', max_length=30, blank=True, default='')
    complemento = models.CharField(verbose_name='Complemento', max_length=120, blank=True, default='')
    bairro = models.CharField(verbose_name='Bairro', max_length=100, blank=True, default='')
    endereco_eletronico = models.EmailField(verbose_name='Endereço eletrônico (e-mail)', blank=True, default='')
    descricao_extrato_bancario = models.CharField(
        verbose_name='Texto no extrato bancário',
        max_length=255,
        blank=True,
        default='',
        help_text='Trecho que aparece no histórico do extrato para este CNPJ. Usado na conciliação automática de contas a receber quando CNPJ e nome curto não batem.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "cnpj"],
                name="fornecedor_unico_cnpj_por_empresa",
            ),
        ]

    def save(self, *args, **kwargs):
        self.cnpj = limpar_cnpj(self.cnpj)
        self.cep = limpar_cep(self.cep)
        self.telefone = limpar_telefone_br(self.telefone)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.razao


class SocioFornecedor(models.Model):
    """Sócio vinculado ao fornecedor (opcional no cadastro)."""

    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.CASCADE,
        related_name="socios",
        verbose_name="Fornecedor",
    )
    nome = models.CharField(verbose_name="Nome", max_length=200)
    tipo_qualificacao = models.CharField(
        verbose_name="Qualificação",
        max_length=100,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "Sócio do fornecedor"
        verbose_name_plural = "Sócios do fornecedor"
        ordering = ["id"]

    def __str__(self):
        return self.nome
