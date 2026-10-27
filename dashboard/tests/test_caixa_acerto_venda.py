from django.test import SimpleTestCase

from dashboard.conta_azul.caixa_acerto_venda import caixa_acerto_de_venda_ca
from dashboard.conta_azul.venda_nfse import _item_pagamento_de_venda


class CaixaAcertoVendaTest(SimpleTestCase):
    def test_pagamento_tipo_pagamento_condicao(self):
        envelope = {
            'venda': {
                'condicao_pagamento': {
                    'tipo_pagamento': 'PIX_PAGAMENTO_INSTANTANEO',
                },
            },
        }
        item = _item_pagamento_de_venda(envelope)
        self.assertEqual(item.get('metodo_pagamento'), 'PIX_PAGAMENTO_INSTANTANEO')

    def test_caixa_sem_empresa_id_retorna_vazio(self):
        self.assertEqual(caixa_acerto_de_venda_ca(0, {}), '')
