from datetime import date
from decimal import Decimal

from django.test import TestCase

from contasareceber.models import ContaAReceber
from dashboard.conta_azul.conciliacao import (
    _score_texto,
    _score_valor,
    _tokens_busca,
    sugerir_titulos_para_lancamento,
)
from empresa.models import Empresa
from extrato.models import Banco, ContaBancaria, Lancamento


class ConciliacaoSugestaoTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Conc Test', cnpj='12345678000188')
        self.banco = Banco.objects.create(codigo='001', nome='BB')
        self.conta = ContaBancaria.objects.create(
            empresa=self.empresa,
            banco=self.banco,
            descricao='Stone',
            agencia='1',
            conta='1',
            status='A',
        )

    def test_tokens_busca_extrai_numeros_nfs(self):
        tokens = _tokens_busca('Recebimento vendas NFS-e 5122')
        self.assertIn('5122', tokens)

    def test_score_valor_exato(self):
        self.assertEqual(_score_valor(Decimal('100'), Decimal('100')), 40)

    def test_score_texto_doc(self):
        self.assertGreater(_score_texto(['5122'], '5122', 'cliente'), 0)

    def test_sugerir_car_por_doc_e_valor(self):
        lanc = Lancamento.objects.create(
            empresa=self.empresa,
            conta=self.conta,
            banco=self.banco,
            data=date(2026, 9, 16),
            historico='Recebimento vendas - Mastercard | Crédito',
            valor=Decimal('436.67'),
            conciliado=False,
            fitid='fit-1',
            hash_unico='test-conc-ca-1',
        )
        ContaAReceber.objects.create(
            empresa=self.empresa,
            cliente='Cliente Teste',
            data_vencimento=date(2026, 9, 17),
            valor_a_receber=Decimal('436.67'),
            doc='5122',
            parcela='1/6',
            status='pendente',
            conta_azul_parcela_id='uuid-ca-5122',
        )
        sugestoes = sugerir_titulos_para_lancamento(
            lanc,
            busca='5122',
            periodo_de=date(2026, 9, 1),
            periodo_ate=date(2026, 9, 30),
        )
        receber = [s for s in sugestoes if s.tipo == 'receber']
        self.assertTrue(receber)
        self.assertTrue(receber[0].sync_ca)
        self.assertGreater(receber[0].score, 30)

    def test_sugerir_receber_sem_match_exato_valor(self):
        lanc = Lancamento.objects.create(
            empresa=self.empresa,
            conta=self.conta,
            banco=self.banco,
            data=date(2026, 9, 16),
            historico='Recebimento vendas - Mastercard | Crédito',
            valor=Decimal('3711.51'),
            conciliado=False,
            fitid='fit-2',
            hash_unico='test-conc-ca-2',
        )
        ContaAReceber.objects.create(
            empresa=self.empresa,
            cliente='Cliente parcela',
            data_vencimento=date(2026, 9, 17),
            valor_a_receber=Decimal('436.67'),
            doc='5122',
            parcela='1/6',
            status='pendente',
        )
        sugestoes = sugerir_titulos_para_lancamento(
            lanc,
            periodo_de=date(2026, 9, 1),
            periodo_ate=date(2026, 9, 30),
        )
        receber = [s for s in sugestoes if s.tipo == 'receber']
        self.assertTrue(receber, 'Deve listar contas a receber mesmo sem valor igual ao depósito')
