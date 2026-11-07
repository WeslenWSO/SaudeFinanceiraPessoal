from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from contasareceber.nf_sync_discriminacao import sincronizar_forma_e_autorizacao_nota


class NfSyncDiscriminacaoTests(SimpleTestCase):
    def test_sincroniza_autorizacao_e_forma_na_nota_e_car(self):
        nota = MagicMock()
        nota.pk = 1
        nota.numero_nota = '123'
        nota.discriminacao = 'PIX AUT 123456'
        nota.nsu = ''
        nota.forma_pagamento_id = None
        nota.forma_pagamento = None
        nota.valor_bruto = 100
        nota.valor_liquido = 100

        cob = MagicMock()
        cob.pk = 9
        cob.descricao = 'PIX'

        with patch(
            'contasareceber.nf_sync_discriminacao.detectar_forma_pagamento_e_vincular',
            return_value=(cob, '', None),
        ), patch(
            'contasareceber.nf_sync_discriminacao.extrair_autorizacao',
            return_value='123456',
        ), patch(
            'contasareceber.nf_sync_discriminacao.Cobranca.objects.all',
            return_value=[cob],
        ), patch(
            'contasareceber.socio_sync.propagar_forma_pagamento_nota_para_contas_receber',
            return_value=2,
        ) as prop_fp, patch(
            'contasareceber.socio_sync.propagar_autorizacao_nota_para_contas_receber',
            return_value=2,
        ) as prop_aut:
            res = sincronizar_forma_e_autorizacao_nota(nota)

        self.assertEqual(res['forma'], 'PIX')
        self.assertEqual(res['autorizacao'], '123456')
        nota.save.assert_called()
        prop_fp.assert_called_once_with(nota)
        prop_aut.assert_called_once_with(nota, apenas_vazias=False)
