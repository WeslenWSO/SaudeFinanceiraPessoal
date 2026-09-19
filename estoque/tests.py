from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from openpyxl import Workbook

from empresa.models import Empresa
from estoque.import_planilha import importar_produtos_estoque, parse_planilha_produtos
from estoque.models import ProdutoEstoque


class ProdutoEstoqueModelTest(TestCase):
    def test_str_e_campos(self):
        emp = Empresa.objects.create(razao='Loja Teste', cnpj='12345678000177')
        p = ProdutoEstoque.objects.create(
            empresa=emp,
            codigo_produto='P001',
            descricao='Produto A',
            marca='Marca X',
            quantidade_estoque=Decimal('10.500'),
            valor_ultima_compra=Decimal('12.3456'),
            valor_custo_medio=Decimal('11.0000'),
            valor_custo_contabil=Decimal('11.2000'),
        )
        self.assertIn('P001', str(p))
        self.assertEqual(p.quantidade_estoque, Decimal('10.500'))


def _xlsx_bytes(rows: list[tuple]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ImportPlanilhaEstoqueTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Loja Teste', cnpj='12345678000177')

    def test_importa_e_atualiza_por_codigo(self):
        content = _xlsx_bytes([
            (
                'Código do produto',
                'Descrição do produto',
                'Marca',
                'Quantidade em estoque',
                'Estoque contábil',
                'Valor da última compra',
                'Valor custo médio',
                'Valor custo contábil',
            ),
            ('A1', 'Produto A', 'M1', 5, 5, 10, 9, 9.5),
        ])
        linhas, erros = parse_planilha_produtos(content)
        self.assertEqual(erros, [])
        self.assertEqual(len(linhas), 1)
        stats = importar_produtos_estoque(self.empresa.pk, linhas)
        self.assertEqual(stats['criados'], 1)
        p = ProdutoEstoque.objects.get(codigo_produto='A1')
        self.assertEqual(p.quantidade_estoque, Decimal('5'))

        content2 = _xlsx_bytes([
            (
                'Código do produto',
                'Descrição do produto',
                'Marca',
                'Quantidade em estoque',
                'Estoque contábil',
                'Valor da última compra',
                'Valor custo médio',
                'Valor custo contábil',
            ),
            ('A1', 'Produto A novo', 'M2', 7, 6, 11, 10, 10),
        ])
        linhas2, _ = parse_planilha_produtos(content2)
        stats2 = importar_produtos_estoque(self.empresa.pk, linhas2)
        self.assertEqual(stats2['atualizados'], 1)
        p.refresh_from_db()
        self.assertEqual(p.descricao, 'Produto A novo')
        self.assertEqual(p.quantidade_estoque, Decimal('7'))
