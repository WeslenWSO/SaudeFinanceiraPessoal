from django.test import SimpleTestCase

from contasareceber.cartao_aproximacao import autorizacoes_equivalentes


class AutorizacaoStoneTests(SimpleTestCase):
    def test_sufixo_stone_casa_nf_curta_com_id_longo(self):
        self.assertTrue(
            autorizacoes_equivalentes('15558', '37262949815558', 'STONE')
        )

    def test_aut_debito_69750_no_id_stone(self):
        self.assertTrue(
            autorizacoes_equivalentes('69750', '40363662069750', 'STONE')
        )

    def test_autorizacoes_diferentes_nao_casam(self):
        self.assertFalse(
            autorizacoes_equivalentes('15558', '9999912345', 'STONE')
        )
