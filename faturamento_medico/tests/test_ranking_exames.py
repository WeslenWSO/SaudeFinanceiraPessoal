from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from faturamento_medico.ranking_exames import montar_ranking_exames_qs


class RankingExamesTests(SimpleTestCase):
    def test_agrega_por_exame_e_convenio(self):
        item1 = MagicMock(servico='US - Abdome', total=Decimal('100'), valor=Decimal('100'))
        item2 = MagicMock(servico='US - Abdome', total=Decimal('50'), valor=Decimal('50'))
        fat = MagicMock(convenio='GEAP', servico='', total=Decimal('0'))
        fat.itens_servico.all.return_value = [item1, item2]

        qs = MagicMock()
        qs.prefetch_related.return_value.order_by.return_value = [fat]

        out = montar_ranking_exames_qs(qs)
        self.assertEqual(out['total_quantidade'], 2)
        self.assertEqual(out['total_valor'], Decimal('150'))
        self.assertEqual(out['ranking_exames'][0]['exame'], 'US - Abdome')
        self.assertEqual(out['ranking_exames'][0]['quantidade'], 2)

    def test_filtro_modalidade(self):
        item_us = MagicMock(servico='US - Abdome', modalidade='US', total=Decimal('100'), valor=Decimal('100'))
        item_mr = MagicMock(servico='RM Crânio', modalidade='MR', total=Decimal('200'), valor=Decimal('200'))
        fat = MagicMock(convenio='GEAP', servico='', total=Decimal('0'), observacao='')
        fat.itens_servico.all.return_value = [item_us, item_mr]

        qs = MagicMock()
        qs.prefetch_related.return_value.order_by.return_value = [fat]

        out = montar_ranking_exames_qs(qs, modalidades_filtro=['MR'])
        self.assertEqual(out['total_quantidade'], 1)
        self.assertEqual(out['total_valor'], Decimal('200'))
        self.assertEqual(out['ranking_exames'][0]['exame'], 'RM Crânio')
