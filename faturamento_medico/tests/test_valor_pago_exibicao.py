from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from faturamento_medico.services.valor_pago_exibicao import (
    mapear_valor_pago_itens_grade,
    sincronizar_valor_pago_apos_preco,
    valor_agregacao_analises,
    valor_pago_grade_item,
    valor_pago_para_exibicao,
)


def _item(**kwargs):
    base = {
        'valor': Decimal('220'),
        'total': Decimal('220'),
        'valor_desconto': Decimal('0'),
        'valor_acrescimo': Decimal('0'),
        'valor_pago': None,
        'conferido': False,
    }
    base.update(kwargs)
    return MagicMock(**base)


class ValorPagoExibicaoTest(SimpleTestCase):
    def test_acrescimo_no_ris_maior_que_tabela(self):
        item = _item(valor_pago=Decimal('300'))
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('300'))

    def test_conferido_ignora_valor_pago_desatualizado_do_ris(self):
        item = _item(total=Decimal('80'), valor_pago=Decimal('160'), conferido=True)
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('80'))

    def test_ris_duplica_valor_pago_mesmo_sem_conferir(self):
        item = _item(total=Decimal('350'), valor_pago=Decimal('700'), conferido=False)
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('350'))

    def test_acrescimo_ris_eco_valor_pago_nao_dobra_grade(self):
        item = _item(
            total=Decimal('80'),
            valor_pago=Decimal('80'),
            valor_acrescimo=Decimal('80'),
            conferido=False,
        )
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('80'))

    def test_tabela_atualizada_maior_que_ris(self):
        item = _item(total=Decimal('250'), valor_pago=Decimal('220'))
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('250'))

    def test_grade_item_desconto_ris_obsoleto_pos_preco(self):
        item = _item(
            total=Decimal('275'),
            valor_pago=Decimal('216.82'),
            valor_desconto=Decimal('58.18'),
        )
        self.assertEqual(valor_pago_grade_item(item), Decimal('275'))

    def test_grade_item_atualiza_preco_sem_desconto_ris(self):
        item = _item(
            total=Decimal('275'),
            valor_pago=Decimal('216.82'),
            valor_desconto=Decimal('0'),
        )
        self.assertEqual(valor_pago_grade_item(item), Decimal('275'))

    def test_mapear_soma_total_igual_nf(self):
        i1 = _item(total=Decimal('275'), valor_pago=Decimal('216.82'))
        i1.pk = 1
        i2 = _item(total=Decimal('275'), valor_pago=Decimal('216.82'))
        i2.pk = 2
        m = mapear_valor_pago_itens_grade([i1, i2], Decimal('550'))
        self.assertEqual(m[1], Decimal('275'))
        self.assertEqual(m[2], Decimal('275'))

    def test_grade_item_mantem_rateio_caixa_quando_total_so_ajuste_tabela(self):
        item = _item(
            total=Decimal('205.70'),
            valor_pago=Decimal('180'),
            valor_desconto=Decimal('25.70'),
            conferido=False,
        )
        self.assertEqual(valor_pago_grade_item(item), Decimal('180'))

    def test_grade_item_corrige_valor_pago_copiado_do_total(self):
        item = _item(
            total=Decimal('205.70'),
            valor_pago=Decimal('205.70'),
            valor_desconto=Decimal('25.70'),
            conferido=False,
        )
        self.assertEqual(valor_pago_grade_item(item), Decimal('180'))

    def test_grade_item_corrige_preco_ris_muito_abaixo_do_conferido(self):
        item = _item(
            total=Decimal('350'),
            valor_pago=Decimal('141.08'),
            valor_desconto=Decimal('208.92'),
            conferido=False,
        )
        self.assertEqual(valor_pago_grade_item(item), Decimal('350'))

    def test_desconto_ris_obsoleto_usa_total_apos_aumento_preco(self):
        item = _item(
            total=Decimal('350'),
            valor_pago=Decimal('141.08'),
            valor_desconto=Decimal('208.92'),
            conferido=False,
        )
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('350'))

    def test_conferido_usa_total_mesmo_com_ris_maior(self):
        item = _item(
            total=Decimal('350'),
            valor_pago=Decimal('141'),
            conferido=True,
        )
        self.assertEqual(valor_pago_para_exibicao(item), Decimal('350'))

    def test_sincronizar_eleva_valor_pago_quando_ris_muito_defasado(self):
        item = MagicMock(
            pk=99,
            total=Decimal('350'),
            valor=Decimal('350'),
            valor_acrescimo=Decimal('0'),
            valor_pago=Decimal('141'),
        )
        with patch('faturamento_medico.services.valor_pago_exibicao.ItemServico') as model:
            model.objects.filter.return_value.update = MagicMock()
            sincronizar_valor_pago_apos_preco(item, forcar=True)
            model.objects.filter.return_value.update.assert_called_with(
                valor_pago=Decimal('350'),
            )
            self.assertEqual(item.valor_pago, Decimal('350'))

    def test_sincronizar_nao_sobe_valor_pago_quando_ajuste_moderado_tabela(self):
        item = MagicMock(
            pk=88,
            total=Decimal('205.70'),
            valor=Decimal('205.70'),
            valor_acrescimo=Decimal('0'),
            valor_pago=Decimal('180'),
        )
        with patch('faturamento_medico.services.valor_pago_exibicao.ItemServico') as model:
            model.objects.filter.return_value.update = MagicMock()
            sincronizar_valor_pago_apos_preco(item, forcar=True)
            model.objects.filter.return_value.update.assert_not_called()

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

    def test_sincronizar_zera_acrescimo_eco_ris(self):
        item = MagicMock(
            pk=11,
            total=Decimal('350'),
            valor=Decimal('350'),
            valor_pago=Decimal('350'),
            valor_acrescimo=Decimal('350'),
        )
        with patch('faturamento_medico.services.valor_pago_exibicao.ItemServico') as model:
            model.objects.filter.return_value.update = MagicMock()
            sincronizar_valor_pago_apos_preco(item, forcar=False)
            model.objects.filter.return_value.update.assert_any_call(
                valor_acrescimo=Decimal('0'),
            )

    def test_sincronizar_corrige_valor_pago_duplicado_do_ris(self):
        item = MagicMock(
            pk=12,
            total=Decimal('80'),
            valor=Decimal('80'),
            valor_acrescimo=Decimal('0'),
            qt=1,
            valor_pago=Decimal('160'),
        )
        with patch('faturamento_medico.services.valor_pago_exibicao.ItemServico') as model:
            model.objects.filter.return_value.update = MagicMock()
            sincronizar_valor_pago_apos_preco(item, forcar=False)
            model.objects.filter.return_value.update.assert_called_once_with(
                valor_pago=Decimal('80'),
            )

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

    def test_agregacao_analises_usa_liquido_quando_ris_menor_que_tabela(self):
        item = _item(total=Decimal('570'), valor_pago=Decimal('220'))
        fat = MagicMock(status_agendamento='Concluído')
        self.assertEqual(valor_agregacao_analises(item, fat), Decimal('570'))

    def test_agregacao_analises_aguardando_sem_pago_usa_total(self):
        item = _item(total=Decimal('150'), valor_pago=None)
        fat = MagicMock(status_agendamento='Aguardando faturamento')
        self.assertEqual(valor_agregacao_analises(item, fat), Decimal('150'))
