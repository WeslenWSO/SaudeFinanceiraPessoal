from django.test import SimpleTestCase

from dashboard.conta_azul.catalogos_fiscais import (
    listar_c_class_trib,
    listar_indicador_operacao,
    listar_nbs,
    naturezas_operacao,
    sugestoes_por_lei_116,
)


class CatalogosFiscaisTest(SimpleTestCase):
    def test_natureza_tem_quatro_opcoes(self):
        self.assertEqual(len(naturezas_operacao()), 4)

    def test_busca_cclasstrib(self):
        itens = listar_c_class_trib(q='000001')
        self.assertTrue(any(i.get('codigo') == '000001' for i in itens))

    def test_sugestao_lei_116_0402(self):
        sug = sugestoes_por_lei_116('04.02')
        self.assertIn('codigo_nbs', sug)
        self.assertIn('indicador_operacao', sug)
        self.assertIn('c_class_trib', sug)

    def test_nbs_filtra_por_lei_116(self):
        geral = listar_nbs(limite=5)
        filtrado = listar_nbs(lei_116='04.02', limite=5)
        self.assertTrue(len(geral) >= len(filtrado) > 0)

    def test_indicador_contem_030101(self):
        itens = listar_indicador_operacao(q='030101')
        self.assertTrue(any(i.get('codigo') == '030101' for i in itens))
