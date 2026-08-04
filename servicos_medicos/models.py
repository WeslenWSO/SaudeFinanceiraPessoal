from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from empresa.models import Empresa

class Convenio(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    nome = models.CharField(verbose_name='Nome do Convênio', max_length=100)
    dia_fechamento = models.PositiveSmallIntegerField(
        verbose_name='Dia para fechamento',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        null=True,
        blank=True,
        help_text='Dia do mês para fechamento do convênio (1 a 31).',
    )
    dia_abertura = models.PositiveSmallIntegerField(
        verbose_name='Dia para abertura',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        null=True,
        blank=True,
        help_text='Dia do mês para abertura do convênio (1 a 31).',
    )
    observacao = models.TextField(
        verbose_name='Observação',
        blank=True,
        default='',
        help_text='Particularidades e regras específicas deste convênio.',
    )

    class Meta:
        verbose_name = 'Convênio'
        verbose_name_plural = 'Convênios'
        ordering = ['nome']

    def __str__(self):
        return self.nome

class ServicosMedicos(models.Model):
    PORTE_CHOICES = [
        (0, '0'),
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5'),
        (6, '6'),
    ]
    codigo = models.CharField(verbose_name='Código', max_length=20, unique=True)
    servicos = models.CharField(verbose_name='Serviços', max_length=200)
    porte_anestesico = models.IntegerField(verbose_name='Porte Anestésico', choices=PORTE_CHOICES, blank=True, null=True)

    class Meta:
        verbose_name = 'Serviço Médico'
        verbose_name_plural = 'Serviços Médicos'
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.servicos}"

class TabelaPreco(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    convenio = models.ForeignKey(Convenio, on_delete=models.CASCADE, verbose_name='Convênio')
    cabecalho = models.ForeignKey('Cabecalho', on_delete=models.CASCADE, verbose_name='Cabeçalho', null=True, blank=True)
    codigo_servico = models.ForeignKey(ServicosMedicos, on_delete=models.CASCADE, verbose_name='Código do Serviço')
    preco_apartamento = models.DecimalField(verbose_name='Preço sem Contraste', max_digits=10, decimal_places=2)
    preco_enfermaria = models.DecimalField(verbose_name='Preço com Contraste', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Tabela de Preço'
        verbose_name_plural = 'Tabelas de Preço'
        ordering = ['empresa', 'convenio', 'cabecalho', 'codigo_servico']
        unique_together = ['empresa', 'convenio', 'cabecalho', 'codigo_servico']

    def __str__(self):
        cabecalho_nome = self.cabecalho.nome_tabela if self.cabecalho else "Sem Cabeçalho"
        return cabecalho_nome


class Cabecalho(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    convenio = models.ForeignKey(Convenio, on_delete=models.CASCADE, verbose_name='Convênio')
    nome_tabela = models.CharField(verbose_name='Nome da Tabela', max_length=100)

    class Meta:
        verbose_name = 'Cabeçalho'
        verbose_name_plural = 'Cabeçalhos'
        ordering = ['empresa', 'convenio', 'nome_tabela']

    def __str__(self):
        return f"{self.empresa} - {self.convenio} - {self.nome_tabela}"
