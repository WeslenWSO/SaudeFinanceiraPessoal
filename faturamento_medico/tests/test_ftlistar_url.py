from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory, SimpleTestCase

from faturamento_medico.views import _tem_filtros_na_query, _url_ftlistar_com_filtros_sessao


class FtlistarUrlHelpersTest(SimpleTestCase):
    def _request(self, query: str = ''):
        rf = RequestFactory()
        path = '/faturamento_medico/'
        req = rf.get(f'{path}?{query}' if query else path)
        req.session = SessionStore()
        return req

    def test_somente_per_page_nao_e_filtro_na_query(self):
        req = self._request('per_page=25')
        self.assertFalse(_tem_filtros_na_query(req))

    def test_data_inicio_na_query_evita_redirect_ciclico(self):
        req = self._request('data_inicio=2025-01-01&data_fim=2025-01-31')
        self.assertTrue(_tem_filtros_na_query(req))

    def test_url_canonica_completa_periodo_quando_sessao_soh_tem_per_page(self):
        req = self._request()
        req.session['faturamento_filters'] = {'per_page': '25'}
        url = _url_ftlistar_com_filtros_sessao(req)
        self.assertIn('data_inicio=', url)
        self.assertIn('data_fim=', url)
        self.assertIn('per_page=25', url)