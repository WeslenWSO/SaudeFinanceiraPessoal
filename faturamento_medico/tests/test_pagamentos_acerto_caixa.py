from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from faturamento_medico.services.pagamentos_acerto_caixa import (
    aplicar_pagamentos_acerto_ao_vincular_nota,
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

    @patch('faturamento_medico.services.pagamentos_acerto_caixa.Cobranca')
    @patch('notasfiscais.utils.detectar_forma_pagamento_e_vincular')
    @patch('notasfiscais.discriminacao_nfse.discriminacao_valor_coerente')
    def test_vincular_nota_preenche_rateio(self, coerente_mock, detectar_mock, CobrancaMock):
        coerente_mock.return_value = True
        cob_dh = MagicMock(pk=1, descricao='DINHEIRO')
        cob_cc = MagicMock(pk=3, descricao='CARTAO CREDITO')
        CobrancaMock.objects.all.return_value = [cob_dh, cob_cc]

        def get(pk):
            return {1: cob_dh, 3: cob_cc}[pk]

        CobrancaMock.objects.get.side_effect = get
        detectar_mock.return_value = (
            None,
            'multi_segmentar',
            [(Decimal('500'), cob_dh), (Decimal('1000'), cob_cc)],
        )

        nota = MagicMock()
        nota.discriminacao = 'PAGAMENTO: DINHEIRO 500 CARTAO 1000'
        nota.valor_liquido = Decimal('1500')
        nota.valor_bruto = Decimal('1500')
        nota.forma_pagamento_id = None

        fat = MagicMock()
        fat.pagamentos_acerto_json = []

        aplicar_pagamentos_acerto_ao_vincular_nota(fat, nota)

        fat.save.assert_called()
        saved = fat.pagamentos_acerto_json
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]['cobranca_id'], 1)
        self.assertEqual(saved[1]['cobranca_id'], 3)
