from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from faturamento_medico.services.pagamentos_acerto_caixa import (
    texto_forma_pgto,
    validar_e_normalizar_pagamentos,
)


class PagamentosAcertoCaixaTest(SimpleTestCase):
    @patch('faturamento_medico.services.pagamentos_acerto_caixa.Cobranca')
    def test_rateio_valido(self, CobrancaMock):
        cob_dh = MagicMock(pk=1, descricao='DINHEIRO')
        cob_cc = MagicMock(pk=3, descricao='CARTAO CREDITO')

        def get(pk):
            return {1: cob_dh, 3: cob_cc}[pk]

        CobrancaMock.objects.get.side_effect = get
        linhas, err = validar_e_normalizar_pagamentos(
            [
                {'cobranca_id': 1, 'valor': '500'},
                {'cobranca_id': 3, 'valor': '1000'},
            ],
            valor_esperado=Decimal('1500'),
        )
        self.assertIsNone(err)
        assert linhas is not None
        self.assertEqual(len(linhas), 2)

    def test_texto_forma_pgto(self):
        t = texto_forma_pgto([
            {'rotulo': 'Dinheiro', 'valor': Decimal('500'), 'valor_fmt': '500,00'},
            {'rotulo': 'Cartão crédito', 'valor': Decimal('1000'), 'valor_fmt': '1.000,00'},
        ])
        self.assertIn('Dinheiro', t)
        self.assertIn('Cartão', t)
