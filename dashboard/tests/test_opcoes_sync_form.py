from django.test import SimpleTestCase
from django.test import RequestFactory

from dashboard.conta_azul.opcoes_sync_form import (
    dica_atualizar_pos_sync,
    flags_from_post,
    montar_opcoes_sync,
    resumo_flags,
)
from datetime import date


class OpcoesSyncFormTests(SimpleTestCase):
    def test_post_respeita_flags_independentes(self):
        rf = RequestFactory()
        req = rf.post('/', {'receitas': 'on', 'despesas': 'on', 'vendas': 'on'})
        flags = flags_from_post(req)
        self.assertTrue(flags['receitas'])
        self.assertTrue(flags['despesas'])
        self.assertTrue(flags['vendas'])
        self.assertFalse(flags['nfse_prestador'])
        self.assertFalse(flags['cadastros'])

    def test_nfse_nao_liga_vendas_automatico(self):
        rf = RequestFactory()
        req = rf.post('/', {'nfse_prestador': 'on'})
        flags = flags_from_post(req)
        self.assertTrue(flags['nfse_prestador'])
        self.assertFalse(flags['vendas'])

    def test_montar_opcoes_sync(self):
        flags = {'receitas': True, 'despesas': False, 'vendas': False,
                 'cadastros': False, 'transferencias': False, 'nfse_prestador': False}
        op = montar_opcoes_sync(flags, data_de=date(2026, 10, 1), data_ate=date(2026, 10, 31))
        self.assertTrue(op['receitas'])
        self.assertFalse(op['despesas'])
        self.assertEqual(op['data_de'].day, 1)
        self.assertTrue(op['receitas_somente_recebidos'])
        op_aberto = montar_opcoes_sync(
            flags, data_de=date(2026, 10, 1), data_ate=date(2026, 10, 31), receitas_todos_status=True
        )
        self.assertFalse(op_aberto['receitas_somente_recebidos'])
        self.assertFalse(op_aberto['receitas_por_recebimento'])

    def test_dica_pos_sync_sem_car_cap(self):
        flags = {
            'cadastros': True,
            'receitas': False,
            'despesas': False,
            'transferencias': False,
            'vendas': True,
            'nfse_prestador': True,
        }
        dica = dica_atualizar_pos_sync(flags)
        self.assertNotIn('Contas a Receber', dica)
        self.assertNotIn('Contas a Pagar', dica)
        self.assertIn('Notas Fiscais', dica)
        self.assertIn('cadastros', dica)
