from django.test import SimpleTestCase

from notasfiscais.utils import extrair_autorizacao


class ExtrairAutorizacaoTests(SimpleTestCase):
    def test_nsu_e_cc_aut(self):
        self.assertEqual(
            extrair_autorizacao('Forma de pagamento: CC AUT: 97044'),
            '97044',
        )
        self.assertEqual(extrair_autorizacao('PGT: CC NSU 123456789'), '123456789')

    def test_autorizacao_acentuada(self):
        self.assertEqual(
            extrair_autorizacao('Cartão de Crédito Autorização: 554433'),
            '554433',
        )
