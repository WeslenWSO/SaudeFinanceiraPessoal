from datetime import date
from decimal import Decimal

from django.test import TestCase

from extrato.models import Banco, ContaBancaria, Lancamento
from extrato.services.stone_conciliacao_previa import (
    parse_stone_historico,
    sugerir_conciliacao_stone,
)
from empresa.models import Empresa
from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao


class StoneConciliacaoPreviaTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Medicinarte', cnpj='12345678000199')
        self.banco = Banco.objects.create(nome='Stone', codigo='999')
        self.conta = ContaBancaria.objects.create(
            empresa=self.empresa,
            banco=self.banco,
            descricao='STONE',
            agencia='1',
            conta='123',
        )
        self.lanc = Lancamento.objects.create(
            empresa=self.empresa,
            conta=self.conta,
            banco=self.banco,
            data=date(2026, 9, 15),
            historico='Recebimento vendas - Elo | Crédito',
            valor=Decimal('374.36'),
            hash_unico='test-stone-374',
            status_importacao='P',
        )

    def test_parse_stone_historico(self):
        parsed = parse_stone_historico('Recebimento vendas - American Express | Crédito')
        self.assertEqual(parsed['bandeira'], 'American Express')
        self.assertEqual(parsed['tipo'], 'credito')

    def test_sugestao_por_valor_e_bandeira(self):
        RelatorioRecebiveisMaquinaCartao.objects.create(
            empresa=self.empresa,
            maquinha='STONE',
            bandeira='Elo',
            forma_pagamento='Crédito',
            data_pagamento=date(2026, 9, 15),
            valor_liquido=Decimal('374.36'),
            valor_bruto=Decimal('380.00'),
            conciliado=False,
            nota_fiscal='12345',
            numero_autorizacao='AUTH1',
        )
        sug = sugerir_conciliacao_stone(self.lanc, self.empresa.pk)
        self.assertIsNotNone(sug)
        self.assertEqual(len(sug['relatorio_ids']), 1)
        self.assertEqual(sug['itens'][0]['nota_fiscal'], '12345')
