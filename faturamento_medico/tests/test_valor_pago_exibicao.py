from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from faturamento_medico.services.valor_pago_exibicao import (
    sincronizar_valor_pago_apos_preco,
    valor_pago_para_exibicao,
)


def _item(**kwargs):
    base = {
        'valor': Decimal('220'),
        'total': Decimal('220'),
        'valor_desconto': Decimal('0'),
        'valor_acrescimo': Decimal('0'),
        'valor_pago': None,
    }
    base.update(kwargs)
    return MagicMock(**base)


class ValorPagoExibicaoTest(SimpleTestCase):
    def test_acrescimo_no_ris_maior_que_tabela(self):
        item = _item(valor_pago=Decimal('300'))
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('300'))

    def test_tabela_atualizada_maior_que_ris(self):
        item = _item(total=Decimal('250'), valor_pago=Decimal('220'))
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('250'))

    def test_liquido_com_acrescimo_cadastrado(self):
        item = _item(valor_acrescimo=Decimal('80'), valor_pago=None)
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('300'))

    def test_sincronizar_nao_apaga_valor_pago_com_acrescimo(self):
        item = MagicMock(
            total=Decimal('220'),
            valor=Decimal('220'),
            valor_pago=Decimal('300'),
        )
        sincronizar_valor_pago_apos_preco(item)
        item.save.assert_not_called()
