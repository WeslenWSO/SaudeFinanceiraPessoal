from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from empresa.models import Empresa
from estoque.models import EntradaEstoqueNota, NaturezaEstoque, ProdutoEstoque
from estoque.services.movimentacao import gerar_entrada_desde_item_nota
from notafiscalentrada.models import NotaFiscalEntrada, NotaFiscalEntradaItem


class EntradaNotaNovoProdutoTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Emp NF', cnpj='12345678000155')
        nf = NotaFiscalEntrada.objects.create(
            empresa=self.empresa,
            tipo_nota='comercio',
            chave_acesso='2' * 44,
            numero_nota='22181',
            serie='1',
            fornecedor_cnpj='12345678000199',
            fornecedor_nome='Fornecedor',
            destinatario_cnpj='12345678000155',
            destinatario_nome='Emp NF',
            data_emissao=timezone.make_aware(datetime(2026, 10, 28, 10, 0)),
        )
        self.item = NotaFiscalEntradaItem.objects.create(
            nota_fiscal=nf,
            numero_item=1,
            codigo_produto='37469',
            nome_produto='Eletrodo descartável',
            cfop='5102',
            quantidade=Decimal('500'),
            valor_unitario=Decimal('0.42'),
            valor_total=Decimal('210'),
            unidade='UND',
        )

    def test_gerar_estoque_cria_produto_quando_codigo_nf_novo(self):
        self.assertFalse(
            ProdutoEstoque.objects.filter(
                empresa=self.empresa,
                codigo_produto='37469',
            ).exists(),
        )
        gerar_entrada_desde_item_nota(self.item, usuario=None, marca='Solidor')
        produto = ProdutoEstoque.objects.get(empresa=self.empresa, codigo_produto='37469')
        self.assertEqual(produto.natureza, NaturezaEstoque.CONSUMIVEL)
        self.assertIn('Eletrodo', produto.descricao)
        self.assertEqual(produto.marca, 'Solidor')
        self.assertTrue(EntradaEstoqueNota.objects.filter(nota_item=self.item, produto=produto).exists())
