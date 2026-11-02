from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from empresa.models import Empresa
from servicos_medicos.models import Cabecalho, Convenio, ServicosMedicos, TabelaPreco
from servicos_medicos.permissoes import usuario_pode_editar_tabela_preco_grid
from servicos_medicos.tabela_preco_grid import ErroGridTabelaPreco, atualizar_linha_grid


class PermissaoGridTests(TestCase):
    def test_saude_ou_superuser(self):
        saude = User.objects.create_user(username="Saude", password="x")
        outro = User.objects.create_user(username="joao", password="x")
        admin = User.objects.create_superuser(username="root", password="x", email="a@b.c")
        self.assertTrue(usuario_pode_editar_tabela_preco_grid(saude))
        self.assertTrue(usuario_pode_editar_tabela_preco_grid(admin))
        self.assertFalse(usuario_pode_editar_tabela_preco_grid(outro))


class AtualizarGridTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razao="Teste LTDA", cnpj="00000000000100", nome_fantasia="Teste"
        )
        self.conv = Convenio.objects.create(empresa=self.empresa, nome="PART")
        self.cab = Cabecalho.objects.create(
            empresa=self.empresa, convenio=self.conv, nome_tabela="TAB"
        )
        self.servico = ServicosMedicos.objects.create(codigo="40802012", servicos="RX ANTIGO")
        self.tp = TabelaPreco.objects.create(
            empresa=self.empresa,
            convenio=self.conv,
            cabecalho=self.cab,
            codigo_servico=self.servico,
            preco_apartamento=Decimal("10.00"),
            preco_enfermaria=Decimal("12.00"),
        )

    def test_atualiza_preco_e_servico(self):
        r = atualizar_linha_grid(
            tabela_preco_id=self.tp.pk,
            empresa_id=self.empresa.pk,
            servicos="RX NOVO",
            preco_apartamento="99.50",
            preco_enfermaria="100",
        )
        self.assertEqual(r["servicos"], "RX NOVO")
        self.servico.refresh_from_db()
        self.tp.refresh_from_db()
        self.assertEqual(self.servico.servicos, "RX NOVO")
        self.assertEqual(self.tp.preco_apartamento, Decimal("99.50"))
        self.assertEqual(self.tp.preco_enfermaria, Decimal("100.00"))

    def test_empresa_errada(self):
        with self.assertRaises(ErroGridTabelaPreco):
            atualizar_linha_grid(
                tabela_preco_id=self.tp.pk,
                empresa_id=99999,
                preco_apartamento="1",
            )
