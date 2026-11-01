from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, SimpleTestCase

from estoque.permissoes import usuario_aprovador_estorno_nf, validar_aprovacao_estorno_nf


class EstornoNfPermissoesTest(SimpleTestCase):
    def test_saude_e_aprovador(self):
        user = User(username='saude')
        self.assertTrue(usuario_aprovador_estorno_nf(user))

    def test_outro_usuario_precisa_senha(self):
        rf = RequestFactory()
        req = rf.post('/', {})
        req.user = User(username='operador')
        ok, msg = validar_aprovacao_estorno_nf(req)
        self.assertFalse(ok)
        self.assertIn('senha', msg.lower())

    def test_anonimo_precisa_senha(self):
        rf = RequestFactory()
        req = rf.post('/', {})
        req.user = AnonymousUser()
        ok, _ = validar_aprovacao_estorno_nf(req)
        self.assertFalse(ok)
