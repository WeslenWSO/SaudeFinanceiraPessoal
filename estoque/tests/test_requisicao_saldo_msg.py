from decimal import Decimal
from unittest.mock import Mock

from django.test import SimpleTestCase

from estoque.services.movimentacao import _msg_saldo_insuficiente, _rotulo_produto_estoque


class RequisicaoSaldoMsgTest(SimpleTestCase):
    def test_rotulo_produto(self):
        p = Mock(codigo_produto='ABC', descricao='Água mineral', pk=1)
        self.assertIn('ABC', _rotulo_produto_estoque(p))
        self.assertIn('Água', _rotulo_produto_estoque(p))

    def test_mensagem_inclui_codigo_e_quantidades(self):
        p = Mock(codigo_produto='123', descricao='Flanela', pk=2)
        msg = _msg_saldo_insuficiente(
            local='Farmácia',
            produto=p,
            disponivel=Decimal('2'),
            solicitado=Decimal('10'),
        )
        self.assertIn('123', msg)
        self.assertIn('Flanela', msg)
        self.assertIn('disponível 2', msg)
        self.assertIn('solicitado 10', msg)
