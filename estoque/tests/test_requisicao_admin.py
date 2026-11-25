from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from empresa.models import Empresa
from estoque.models import (
    MovimentoEstoque,
    ProdutoEstoque,
    RequisicaoEstoque,
    RequisicaoEstoqueItem,
    SaldoEstoqueSetor,
)
from estoque.services.movimentacao import (
    EstoqueErro,
    concluir_requisicao,
    estornar_requisicao_concluida,
    excluir_requisicao_admin,
)
from estoque.setores import SetorEstoque


class RequisicaoAdminEstornoTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Teste', cnpj='11222333000181')
        self.user = User.objects.create_user('admin', password='x')
        self.produto = ProdutoEstoque.objects.create(
            empresa=self.empresa,
            codigo_produto='T1',
            descricao='Teste',
            quantidade_estoque=Decimal('100'),
            valor_custo_medio=Decimal('5'),
        )

    def _req_transferencia(self) -> RequisicaoEstoque:
        req = RequisicaoEstoque.objects.create(
            empresa=self.empresa,
            tipo=RequisicaoEstoque.Tipo.TRANSFERENCIA,
            setor_origem=SetorEstoque.FARMACIA,
            setor_destino=SetorEstoque.ULTRASSON,
            status=RequisicaoEstoque.Status.RASCUNHO,
            criado_por=self.user,
        )
        RequisicaoEstoqueItem.objects.create(
            requisicao=req,
            produto=self.produto,
            quantidade=Decimal('10'),
        )
        return req

    def test_estornar_devolve_farmacia_e_setor(self):
        req = self._req_transferencia()
        concluir_requisicao(req, usuario=self.user)
        req.refresh_from_db()
        self.assertEqual(req.status, RequisicaoEstoque.Status.CONCLUIDA)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.quantidade_estoque, Decimal('90'))
        saldo = SaldoEstoqueSetor.objects.get(produto=self.produto, setor=SetorEstoque.ULTRASSON)
        self.assertEqual(saldo.quantidade, Decimal('10'))

        estornar_requisicao_concluida(req, usuario=self.user, reabrir=True)
        req.refresh_from_db()
        self.assertEqual(req.status, RequisicaoEstoque.Status.RASCUNHO)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.quantidade_estoque, Decimal('100'))
        saldo.refresh_from_db()
        self.assertEqual(saldo.quantidade, Decimal('0'))
        self.assertFalse(MovimentoEstoque.objects.filter(requisicao=req).exists())

    def test_excluir_concluida_remove_registro(self):
        req = self._req_transferencia()
        pk = req.pk
        concluir_requisicao(req, usuario=self.user)
        excluir_requisicao_admin(req, usuario=self.user)
        self.assertFalse(RequisicaoEstoque.objects.filter(pk=pk).exists())
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.quantidade_estoque, Decimal('100'))

    def test_estornar_falha_sem_movimento(self):
        req = RequisicaoEstoque.objects.create(
            empresa=self.empresa,
            tipo=RequisicaoEstoque.Tipo.BAIXA_FARMACIA,
            setor_destino=SetorEstoque.ENFERMAGEM,
            status=RequisicaoEstoque.Status.CONCLUIDA,
            criado_por=self.user,
        )
        with self.assertRaises(EstoqueErro):
            estornar_requisicao_concluida(req, usuario=self.user)