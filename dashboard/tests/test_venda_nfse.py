from django.test import SimpleTestCase

from dashboard.conta_azul.venda_nfse import (
    _garantir_pagamento_na_discriminacao,
    montar_discriminacao_venda_ca,
)


class VendaNfseEnriquecimentoTest(SimpleTestCase):
    def test_discriminacao_com_pagamento_na_venda(self):
        envelope = {
            'venda': {
                'observacao': (
                    'EXAME RX\nPACIENTE: MARIA\nPAGAMENTO: DINHEIRO R$ 150,00'
                ),
            },
        }
        disc = montar_discriminacao_venda_ca(envelope)
        self.assertIn('PAGAMENTO', disc.upper())
        self.assertIn('MARIA', disc)

    def test_garantir_clausula_pagamento(self):
        out = _garantir_pagamento_na_discriminacao('EXAME US', 'Cartão de Crédito')
        self.assertIn('PAGAMENTO:', out)
        self.assertIn('Cartão', out)
