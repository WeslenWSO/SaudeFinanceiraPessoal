from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from empresa.models import Empresa
from estoque.export_planilha import exportar_analise_compra_xlsx
from estoque.models import EntradaEstoqueNota, NaturezaEstoque, ProdutoEstoque
from estoque.services.analise_compra import montar_linhas_analise_compra
from notafiscalentrada.models import NotaFiscalEntrada, NotaFiscalEntradaItem


class AnaliseCompraTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Emp AC', cnpj='12345678000155')
        self.produto = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='P100',
            descricao='Soro',
            marca='Marca A',
            natureza=NaturezaEstoque.CONSUMIVEL,
            unidade='UN',
            unidade_master='CX',
            quantidade_por_master=Decimal('10'),
            quantidade_estoque=Decimal('25'),
            dias_entrega_fornecedor=7,
        )
        nf = NotaFiscalEntrada.objects.create(
            empresa=self.empresa,
            tipo_nota='comercio',
            chave_acesso='1' * 44,
            numero_nota='999',
            serie='1',
            fornecedor_cnpj='12345678000199',
            fornecedor_nome='Fornecedor NF',
            destinatario_cnpj='12345678000155',
            destinatario_nome='Emp AC',
            data_emissao=timezone.make_aware(datetime(2026, 10, 15, 10, 0)),
        )
        item = NotaFiscalEntradaItem.objects.create(
            nota_fiscal=nf,
            numero_item=1,
            codigo_produto='P100',
            nome_produto='Soro',
            cfop='5102',
            quantidade=Decimal('5'),
            valor_unitario=Decimal('2'),
            valor_total=Decimal('10'),
            unidade='UN',
        )
        EntradaEstoqueNota.objects.create(
            nota_item=item,
            produto=self.produto,
            quantidade=Decimal('5'),
            valor_unitario=Decimal('2'),
        )

    def test_montar_linha_ultima_compra(self):
        linhas = montar_linhas_analise_compra(self.empresa.pk)
        self.assertEqual(len(linhas), 1)
        row = linhas[0]
        self.assertEqual(row['codigo_produto'], 'P100')
        self.assertEqual(row['qtd_ultima_compra'], Decimal('5'))
        self.assertEqual(row['data_ultima_compra'].day, 15)
        self.assertEqual(row['fornecedor'], 'Fornecedor NF')
        self.assertEqual(row['estoque'], Decimal('25'))

    def test_export_xlsx_cabecalho(self):
        linhas = montar_linhas_analise_compra(self.empresa.pk)
        data = exportar_analise_compra_xlsx(linhas)
        wb = load_workbook(BytesIO(data))
        headers = [c.value for c in wb.active[1]]
        self.assertEqual(headers[0], 'Código do produto')
        self.assertEqual(wb.active[2][0].value, 'P100')
