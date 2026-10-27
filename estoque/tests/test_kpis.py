from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from empresa.models import Empresa
from estoque.models import MovimentoEstoque, NaturezaEstoque, ProdutoEstoque, SaldoEstoqueSetor
from estoque.setores import SetorEstoque
from estoque.services.kpis import montar_kpis_estoque


class KpisEstoqueServiceTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Emp KPI', nome_fantasia='KPI')

    def test_kpis_vazio_sem_empresa(self):
        data = montar_kpis_estoque(None)
        self.assertEqual(data['farmacia_produtos'], 0)

    def test_conta_produto_e_alerta(self):
        ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='A1',
            descricao='Item A',
            natureza=NaturezaEstoque.CONSUMIVEL,
            quantidade_estoque=Decimal('2'),
            estoque_minimo=Decimal('5'),
            valor_custo_medio=Decimal('10'),
        )
        data = montar_kpis_estoque(self.empresa.pk)
        self.assertEqual(data['farmacia_produtos'], 1)
        self.assertEqual(data['abaixo_minimo'], 1)
        self.assertIn('20,00', data['valor_farmacia_medio_fmt'])

    def test_movimento_mes(self):
        p = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='B1',
            descricao='Item B',
            natureza=NaturezaEstoque.CONSUMIVEL,
        )
        MovimentoEstoque.objects.create(
            empresa=self.empresa,
            produto=p,
            tipo=MovimentoEstoque.Tipo.BAIXA,
            quantidade=Decimal('3'),
            valor_unitario=Decimal('2.5'),
        )
        data = montar_kpis_estoque(self.empresa.pk)
        self.assertEqual(data['mov_baixas_mes'], 1)
        self.assertEqual(len(data['top_saidas_mes']), 1)
        self.assertEqual(data['top_saidas_mes'][0]['qtd'], 3.0)
        self.assertIn('7,50', data['top_saidas_mes'][0]['valor_fmt'])
        self.assertEqual(len(data['chart_12m_labels']), 12)
        self.assertEqual(len(data['chart_12m_qtd']), 12)

    def test_por_setor_entrada_saida(self):
        p = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='C1',
            descricao='Item C',
            natureza=NaturezaEstoque.CONSUMIVEL,
            quantidade_estoque=Decimal('10'),
            valor_custo_medio=Decimal('1'),
        )
        SaldoEstoqueSetor.objects.create(produto=p, setor=SetorEstoque.SEDACAO, quantidade=Decimal('2'))
        MovimentoEstoque.objects.create(
            empresa=self.empresa,
            produto=p,
            tipo=MovimentoEstoque.Tipo.TRANSFERENCIA,
            setor_origem=SetorEstoque.FARMACIA,
            setor_destino=SetorEstoque.SEDACAO,
            quantidade=Decimal('2'),
            valor_unitario=Decimal('1'),
        )
        data = montar_kpis_estoque(self.empresa.pk)
        sedacao = next(r for r in data['por_setor'] if r['setor'] == SetorEstoque.SEDACAO)
        self.assertEqual(sedacao['estoque_qtd'], 2.0)
        self.assertEqual(sedacao['entrada_qtd'], 2.0)


class KpisEstoqueViewTest(TestCase):
    def test_requer_empresa_na_sessao(self):
        user = User.objects.create_user('kpiuser', password='x')
        self.client.force_login(user)
        r = self.client.get(reverse('estoque:kpis'))
        self.assertEqual(r.status_code, 302)
