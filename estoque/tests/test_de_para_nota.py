from django.test import TestCase

from estoque.models import NaturezaEstoque, ProdutoCodigoNotaDePara, ProdutoEstoque
from estoque.services.de_para_nota import (
    buscar_produto_de_para,
    gravar_de_para_nota,
    situacao_codigo_nota,
)
from empresa.models import Empresa


class DeParaNotaTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao='Empresa Teste De-Para',
            cnpj='11222333000181',
        )
        self.produto = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='000919',
            descricao='Primovist',
            natureza=NaturezaEstoque.CONSUMIVEL,
        )

    def test_situacao_exige_vinculo_quando_codigo_nf_diferente(self):
        sit = situacao_codigo_nota(self.empresa.pk, '80599404', None)
        self.assertTrue(sit['precisa_vinculo'])
        self.assertIsNone(sit['produto_destino'])

    def test_de_para_resolve_produto(self):
        gravar_de_para_nota(self.empresa, '80599404', None, self.produto, global_fornecedor=True)
        p = buscar_produto_de_para(self.empresa.pk, '80599404', None)
        self.assertEqual(p.pk, self.produto.pk)
        sit = situacao_codigo_nota(self.empresa.pk, '80599404', None)
        self.assertFalse(sit['precisa_vinculo'])
        self.assertTrue(sit['via_de_para'])

    def test_mesmo_codigo_nao_precisa_vinculo(self):
        ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='ABC',
            descricao='Item',
            natureza=NaturezaEstoque.CONSUMIVEL,
        )
        sit = situacao_codigo_nota(self.empresa.pk, 'ABC', None)
        self.assertFalse(sit['precisa_vinculo'])
