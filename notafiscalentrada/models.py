from django.db import models
from empresa.models import Empresa
from fornecedor.models import Fornecedor
from categoria.models import Categoria
from cobranca.models import Cobranca
from extrato.models import ContaBancaria
from regrarateio.models import RegraRateio

class NotaFiscalEntrada(models.Model):
    """Modelo para armazenar notas fiscais de entrada (compras)"""

    TIPO_NOTA_CHOICES = [
        ('tomador', 'Nota de Tomador'),
        ('comercio', 'Nota de Comércio'),
    ]

    STATUS_CHOICES = [
        ('importada', 'Importada'),
        ('processada', 'Processada'),
        ('erro', 'Erro'),
    ]

    # Empresa
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')

    # Dados da NF-e
    tipo_nota = models.CharField(verbose_name='Tipo de Nota', max_length=20, choices=TIPO_NOTA_CHOICES)
    chave_acesso = models.CharField(verbose_name='Chave de Acesso', max_length=44, unique=True)
    numero_nota = models.CharField(verbose_name='Número da Nota', max_length=20)
    serie = models.CharField(verbose_name='Série', max_length=10)
    modelo = models.CharField(verbose_name='Modelo', max_length=5, default='55')

    # Emitente (Fornecedor)
    fornecedor_cnpj = models.CharField(verbose_name='CNPJ Fornecedor', max_length=18)
    fornecedor_nome = models.CharField(verbose_name='Nome Fornecedor', max_length=200)
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Fornecedor Vinculado')

    # Destinatário (Empresa)
    destinatario_cnpj = models.CharField(verbose_name='CNPJ Destinatário', max_length=18)
    destinatario_nome = models.CharField(verbose_name='Nome Destinatário', max_length=200)

    # Datas
    data_emissao = models.DateTimeField(verbose_name='Data de Emissão')
    data_saida_entrada = models.DateTimeField(verbose_name='Data Saída/Entrada', null=True, blank=True)

    # Valores
    valor_produtos = models.DecimalField(verbose_name='Valor dos Produtos', max_digits=12, decimal_places=2, default=0)
    valor_frete = models.DecimalField(verbose_name='Valor do Frete', max_digits=12, decimal_places=2, default=0)
    valor_seguro = models.DecimalField(verbose_name='Valor do Seguro', max_digits=12, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(verbose_name='Valor do Desconto', max_digits=12, decimal_places=2, default=0)
    valor_ii = models.DecimalField(verbose_name='Valor do II', max_digits=12, decimal_places=2, default=0)
    valor_ipi = models.DecimalField(verbose_name='Valor do IPI', max_digits=12, decimal_places=2, default=0)
    valor_pis = models.DecimalField(verbose_name='Valor do PIS', max_digits=12, decimal_places=2, default=0)
    valor_cofins = models.DecimalField(verbose_name='Valor do COFINS', max_digits=12, decimal_places=2, default=0)
    valor_icms = models.DecimalField(verbose_name='Valor do ICMS', max_digits=12, decimal_places=2, default=0)
    valor_total = models.DecimalField(verbose_name='Valor Total', max_digits=12, decimal_places=2, default=0)

    # Status e controle
    status = models.CharField(verbose_name='Status', max_length=20, choices=STATUS_CHOICES, default='importada')
    xml_content = models.TextField(verbose_name='Conteúdo XML', blank=True)
    observacoes = models.TextField(verbose_name='Observações', blank=True)

    # Relacionamentos editáveis
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Categoria')
    forma_pagamento = models.ForeignKey(Cobranca, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Forma de Pagamento')

    # Timestamps
    data_importacao = models.DateTimeField(verbose_name='Data de Importação', auto_now_add=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Nota Fiscal de Entrada'
        verbose_name_plural = 'Notas Fiscais de Entrada'
        ordering = ['-data_emissao', '-numero_nota']
        unique_together = ['empresa', 'chave_acesso']

    def save(self, *args, **kwargs):
        # Verificar se deve criar conta a pagar automaticamente
        criar_conta = False
        if self.pk is None:  # Novo registro
            criar_conta = True
        else:  # Atualização
            # Verificar se categoria ou forma_pagamento foram definidos
            old_instance = NotaFiscalEntrada.objects.get(pk=self.pk)
            if (not old_instance.categoria and self.categoria) or (not old_instance.forma_pagamento and self.forma_pagamento):
                criar_conta = True

        # Salvar a nota fiscal primeiro
        super().save(*args, **kwargs)

        # Criar conta a pagar automaticamente se necessário
        if criar_conta and self.categoria and self.forma_pagamento:
            self._criar_conta_a_pagar_automaticamente()

    def _criar_conta_a_pagar_automaticamente(self):
        """Cria conta a pagar automaticamente quando categoria e forma de pagamento estão definidas"""
        from contasapagar.models import ContasaPagar
        from cobranca.models import Cobranca
        from extrato.models import ContaBancaria
        from datetime import timedelta
        from regrarateio.models import RegraRateioItem

        try:
            # Verificar se já existe conta a pagar para esta nota
            if ContasaPagar.objects.filter(
                numdoc=self.numero_nota,
                fornecedor=self.fornecedor
            ).exists():
                return  # Já existe, não criar duplicata

            # Verificar se a empresa utiliza rateio
            if self.regra_rateio and self.regra_rateio.rateio == 'S':
                # Criar contas a pagar para cada sócio conforme a regra de rateio
                if self.regra_rateio:
                    itens_rateio = RegraRateioItem.objects.filter(regrarateio=self.regra_rateio)
                    for item in itens_rateio:
                        # Calcular valor proporcional ao percentual do sócio
                        valor_socio = self.valor_total * (item.percRateio / 100)

                        # Buscar cobrança padrão
                        cobranca = Cobranca.objects.first()
                        if not cobranca:
                            cobranca = Cobranca.objects.create(descricao='COBRANCA_PADRAO', tpag='00')

                        # Buscar conta bancária padrão da empresa
                        conta_banco = ContaBancaria.objects.filter(empresa=self.empresa, status='A').first()

                        # Calcular data de vencimento (30 dias após emissão)
                        data_vencimento = self.data_emissao.date() + timedelta(days=30) if self.data_emissao else None

                        # Criar conta a pagar para o sócio
                        ContasaPagar.objects.create(
                            fornecedor=self.fornecedor,
                            descricao=f'NF {self.numero_nota} - {self.fornecedor_nome} - {item.socios}',
                            numdoc=self.numero_nota,
                            valorDoc=valor_socio,
                            categoria=self.categoria,
                            cobranca=self.forma_pagamento or cobranca,
                            conta_banco=conta_banco,
                            parcela='1',
                            dtEmissao=self.data_emissao.date() if self.data_emissao else None,
                            dtvenc=data_vencimento,
                            status='pendente',
                            obs=f'Gerado automaticamente da NF-e {self.numero_nota} - Rateio: {item.percRateio}% para {item.socios}'
                        )
                else:
                    # Se não há regra de rateio definida, criar conta única
                    self._criar_conta_unica()
            else:
                # Empresa não utiliza rateio, criar conta única
                self._criar_conta_unica()

        except Exception as e:
            # Log do erro mas não interromper o salvamento da nota
            print(f"Erro ao criar conta a pagar automaticamente para NF {self.numero_nota}: {str(e)}")

    def _criar_conta_unica(self):
        """Cria uma única conta a pagar"""
        from contasapagar.models import ContasaPagar
        from cobranca.models import Cobranca
        from extrato.models import ContaBancaria
        from datetime import timedelta

        # Buscar cobrança padrão
        cobranca = Cobranca.objects.first()
        if not cobranca:
            cobranca = Cobranca.objects.create(descricao='COBRANCA_PADRAO', tpag='00')

        # Buscar conta bancária padrão da empresa
        conta_banco = ContaBancaria.objects.filter(empresa=self.empresa, status='A').first()

        # Calcular data de vencimento (30 dias após emissão)
        data_vencimento = self.data_emissao.date() + timedelta(days=30) if self.data_emissao else None

        # Criar conta a pagar
        ContasaPagar.objects.create(
            fornecedor=self.fornecedor,
            descricao=f'NF {self.numero_nota} - {self.fornecedor_nome}',
            numdoc=self.numero_nota,
            valorDoc=self.valor_total,
            categoria=self.categoria,
            cobranca=self.forma_pagamento or cobranca,
            conta_banco=conta_banco,
            parcela='1',
            dtEmissao=self.data_emissao.date() if self.data_emissao else None,
            dtvenc=data_vencimento,
            status='pendente',
            obs=f'Gerado automaticamente da NF-e {self.numero_nota}'
        )

    def __str__(self):
        return f"NF-e {self.numero_nota} - {self.fornecedor_nome} - R$ {self.valor_total}"

    def get_valor_impostos(self):
        """Retorna o valor total de impostos"""
        return self.valor_pis + self.valor_cofins + self.valor_icms + self.valor_ipi + self.valor_ii

    def get_valor_liquido(self):
        """Retorna o valor líquido (produtos + frete + seguro - desconto)"""
        return self.valor_produtos + self.valor_frete + self.valor_seguro - self.valor_desconto


class NotaFiscalEntradaItem(models.Model):
    """Modelo para itens da nota fiscal de entrada"""

    nota_fiscal = models.ForeignKey(NotaFiscalEntrada, on_delete=models.CASCADE, related_name='itens', verbose_name='Nota Fiscal')

    # Dados do produto
    numero_item = models.IntegerField(verbose_name='Número do Item')
    codigo_produto = models.CharField(verbose_name='Código do Produto', max_length=50)
    ean = models.CharField(verbose_name='EAN', max_length=20, blank=True)
    nome_produto = models.CharField(verbose_name='Nome do Produto', max_length=200)
    ncm = models.CharField(verbose_name='NCM', max_length=10, blank=True)
    cest = models.CharField(verbose_name='CEST', max_length=10, blank=True)
    cfop = models.CharField(verbose_name='CFOP', max_length=5)

    # Quantidade e valores
    unidade = models.CharField(verbose_name='Unidade', max_length=10)
    quantidade = models.DecimalField(verbose_name='Quantidade', max_digits=12, decimal_places=4)
    valor_unitario = models.DecimalField(verbose_name='Valor Unitário', max_digits=12, decimal_places=4)
    valor_total = models.DecimalField(verbose_name='Valor Total', max_digits=12, decimal_places=2)

    # Impostos
    valor_pis = models.DecimalField(verbose_name='Valor PIS', max_digits=12, decimal_places=2, default=0)
    valor_cofins = models.DecimalField(verbose_name='Valor COFINS', max_digits=12, decimal_places=2, default=0)
    valor_icms = models.DecimalField(verbose_name='Valor ICMS', max_digits=12, decimal_places=2, default=0)
    valor_ipi = models.DecimalField(verbose_name='Valor IPI', max_digits=12, decimal_places=2, default=0)
    valor_ii = models.DecimalField(verbose_name='Valor II', max_digits=12, decimal_places=2, default=0)

    # Categoria e rateio
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Categoria')
    regra_rateio = models.ForeignKey(RegraRateio, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Regra de Rateio')

    class Meta:
        verbose_name = 'Item da Nota Fiscal de Entrada'
        verbose_name_plural = 'Itens da Nota Fiscal de Entrada'
        ordering = ['numero_item']
        unique_together = ['nota_fiscal', 'numero_item']

    def __str__(self):
        return f"Item {self.numero_item} - {self.nome_produto}"
