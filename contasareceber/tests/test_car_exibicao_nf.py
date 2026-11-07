from unittest.mock import MagicMock, PropertyMock, patch

from django.test import SimpleTestCase

from contasareceber.models import ContaAReceber


class CarExibicaoNfTests(SimpleTestCase):
    def test_cobranca_e_autorizacao_no_proprio_car(self):
        fp = MagicMock(descricao='PIX', pk=1)
        conta = ContaAReceber(autorizacao='AUTH1', forma_pagamento_id=1)
        with patch.object(
            type(conta),
            'forma_pagamento',
            new_callable=PropertyMock,
            return_value=fp,
        ):
            self.assertEqual(conta.get_autorizacao_exibicao(), 'AUTH1')
            self.assertEqual(conta.get_cobranca_exibicao(), 'PIX')
            self.assertFalse(conta.exibe_cobranca_da_nf())

    def test_fallback_autorizacao_via_nota(self):
        conta = ContaAReceber(autorizacao='', forma_pagamento_id=None)
        conta.nota_id = 99
        fake_nota = object()
        with patch.object(
            type(conta),
            'nota',
            new_callable=PropertyMock,
            return_value=fake_nota,
        ), patch(
            'contasareceber.socio_sync._autorizacao_da_nota',
            return_value='NSU123',
        ):
            self.assertEqual(conta.get_autorizacao_exibicao(), 'NSU123')
            self.assertTrue(conta.exibe_autorizacao_da_nf())
