from decimal import Decimal

from django.test import TestCase

from empresa.models import Empresa
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
