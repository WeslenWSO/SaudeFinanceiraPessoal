from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from empresa.models import Empresa
from estoque.models import ProdutoEstoque
from inventario.backup_estoque import aplicar_contagem_ao_estoque, criar_backup_estoque
from inventario.models import EstoqueBackup, Inventario, InventarioItem, InventarioResponsavelContagem
from inventario.services import popular_itens_do_estoque, salvar_responsaveis, usuario_pode_contar


class InventarioModelTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Empresa Teste', cnpj='12345678000199')
        self.produto = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='P001',
            descricao='Produto A',
            quantidade_estoque=Decimal('10.000'),
        )

    def test_diferenca_e_feedback(self):
        inv = Inventario.objects.create(empresa=self.empresa, descricao='Inv')
        item = InventarioItem.objects.create(
            inventario=inv,
            produto=self.produto,
            codigo_produto='P001',
            descricao_produto='Produto A',
            quantidade_estoque=Decimal('10.000'),
            contagem_1=Decimal('10.000'),
            contagem_2=Decimal('9.000'),
        )
        self.assertEqual(item.diff_1, Decimal('0'))
        self.assertEqual(item.diff_2, Decimal('-1.000'))
        feedback = item.feedback_contagens()
        self.assertTrue(any('confere' in m for m in feedback))
        self.assertTrue(any('diverge' in m for m in feedback))


class InventarioFluxoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Empresa Teste', cnpj='12345678000199')
        self.contador = User.objects.create_user('contador', password='x')
        self.outro = User.objects.create_user('outro', password='x')
        ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='P001',
            descricao='Produto A',
            quantidade_estoque=Decimal('5.000'),
        )
        self.client = Client()
        self.client.login(username='contador', password='x')

    def test_contagem_grava_usuario_e_data(self):
        inv = Inventario.objects.create(empresa=self.empresa, descricao='Inv')
        popular_itens_do_estoque(inv)
        salvar_responsaveis(inv, {1: [self.contador], 2: [], 3: []})
        session = self.client.session
        session['empresa_id'] = self.empresa.pk
        session.save()

        url = reverse('inventario:inventario_contagem', kwargs={'pk': inv.pk, 'rodada': 1})
        item = inv.itens.get()
        response = self.client.post(
            url,
            {
                'r1-TOTAL_FORMS': '1',
                'r1-INITIAL_FORMS': '1',
                'r1-MIN_NUM_FORMS': '0',
                'r1-MAX_NUM_FORMS': '1000',
                'r1-0-id': str(item.pk),
                'r1-0-contagem_valor': '5.000',
            },
        )
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.contagem_1, Decimal('5.000'))
        self.assertEqual(item.contagem_1_por, self.contador)
        self.assertIsNotNone(item.contagem_1_em)

    def test_usuario_nao_autorizado_nao_conta(self):
        inv = Inventario.objects.create(empresa=self.empresa, descricao='Inv')
        popular_itens_do_estoque(inv)
        salvar_responsaveis(inv, {1: [self.outro], 2: [], 3: []})
        self.assertFalse(usuario_pode_contar(inv, self.contador, 1))

        session = self.client.session
        session['empresa_id'] = self.empresa.pk
        session.save()
        url = reverse('inventario:inventario_contagem', kwargs={'pk': inv.pk, 'rodada': 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)


class InventarioBackupEstoqueTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Empresa Teste', cnpj='12345678000199')
        self.user = User.objects.create_user('admin_inv', password='x')
        self.produto = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='P001',
            descricao='Produto A',
            quantidade_estoque=Decimal('10.000'),
        )
        self.inv = Inventario.objects.create(empresa=self.empresa, descricao='Inv')

    def test_backup_e_aplicar_contagem(self):
        bkp = criar_backup_estoque(self.inv, self.user)
        self.assertEqual(bkp.linhas.count(), 1)
        self.assertEqual(EstoqueBackup.objects.filter(inventario=self.inv).count(), 1)

        item = InventarioItem.objects.create(
            inventario=self.inv,
            produto=self.produto,
            codigo_produto='P001',
            descricao_produto='Produto A',
            quantidade_estoque=Decimal('10.000'),
            contagem_2=Decimal('8.000'),
        )
        self.inv.rodada_atualiza_estoque = 2
        self.inv.save(update_fields=['rodada_atualiza_estoque'])

        stats = aplicar_contagem_ao_estoque(self.inv, self.user)
        self.assertEqual(stats['atualizados'], 1)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.quantidade_estoque, Decimal('8.000'))
