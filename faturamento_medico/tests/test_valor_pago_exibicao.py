from decimal import Decimal
from unittest.mock import MagicMock, patch

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

    def test_sincronizar_forcar_atualiza_valor_pago_maior_que_tabela(self):
        item = MagicMock(
            pk=7,
            total=Decimal('856.10'),
            valor=Decimal('856.10'),
            valor_pago=Decimal('1070.12'),
        )
        with patch('faturamento_medico.services.valor_pago_exibicao.ItemServico') as model:
            model.objects.filter.return_value.update = MagicMock()
            sincronizar_valor_pago_apos_preco(item, forcar=True)
            model.objects.filter.assert_called_once_with(pk=7)
            model.objects.filter.return_value.update.assert_called_once_with(
                valor_pago=Decimal('856.10'),
            )
            self.assertEqual(item.valor_pago, Decimal('856.10'))
