# nfse_rio_branco/services/riobranco_ws.py
from __future__ import annotations
import time
import requests
from requests.exceptions import HTTPError
from lxml import etree


NS = {"nfse": "http://www.abrasf.org.br/nfse.xsd"}


class RioBrancoWS:
    def __init__(self, endpoint: str, cnpj: str, im: str, senha: str, *,
                 homologacao: bool = True, version: str = "1.00",
                 cert_pem: str | None = None, key_pem: str | None = None,
                 verify_ssl: bool | str = True):
        self.endpoint = endpoint
        self.cnpj = cnpj
        self.im = im
        self.senha = senha
        self.homologa = "true" if homologacao else "false"
        self.version = version
        self.sess = requests.Session()
        if cert_pem and key_pem:
           self.sess.cert = (cert_pem, key_pem)
        self.sess.verify = verify_ssl


    @staticmethod
    def _env(body_xml: str) -> str:
        return (
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
            "xmlns:nfse=\"http://www.abrasf.org.br/nfse.xsd\">"
            "<soapenv:Header/><soapenv:Body>" + body_xml + "</soapenv:Body></soapenv:Envelope>"
        )


    def _ident_requerente(self) -> str:
        return (
           "<nfse:IdentificacaoRequerente>"
           "<nfse:CpfCnpj><nfse:Cnpj>{}</nfse:Cnpj></nfse:CpfCnpj>".format(self.cnpj) +
           f"<nfse:InscricaoMunicipal>{self.im}</nfse:InscricaoMunicipal>" +
           f"<nfse:Senha>{self.senha}</nfse:Senha>" +
           "</nfse:IdentificacaoRequerente>"
        )


    def consultar_nfse_prestador(self, dt_ini: str, dt_fim: str) -> str:
        """Consulta notas emitidas pelo prestador (período AAAA-MM-DD). Retorna XML SOAP de resposta."""
        periodo = f"<nfse:PeriodoEmissao><nfse:DataInicial>{dt_ini}</nfse:DataInicial><nfse:DataFinal>{dt_fim}</nfse:DataFinal></nfse:PeriodoEmissao>"
        pagina = "<nfse:Pagina>1</nfse:Pagina>"
        # Corrigido conforme WSDL v2.03: operação ConsultarNfseServicoPrestado e SOAPAction vazio
        root = "ConsultarNfseServicoPrestadoEnvio"
        soap_action = ""  # SOAPAction vazio conforme WSDL
        body = f"<nfse:{root}>{self._ident_requerente()}{periodo}{pagina}</nfse:{root}>"
        envelope = self._env(body)
        print(f"SOAP Envelope enviado:\n{envelope}")  # Logging detalhado
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.sess.post(self.endpoint, data=envelope.encode("utf-8"), headers={
                       "Content-Type": "text/xml; charset=utf-8",
                       "SOAPAction": soap_action,
                  })
                resp.raise_for_status()
                return resp.text
            except HTTPError as e:
                print(f"Tentativa {attempt + 1}: HTTP {resp.status_code} - {resp.text}")  # Logging da resposta de erro
                if resp.status_code == 500 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                # Melhorar mensagem de erro com detalhes da resposta
                error_msg = f"Erro HTTP {resp.status_code}: {resp.reason}. Resposta: {resp.text[:500]}..." if len(resp.text) > 500 else f"Erro HTTP {resp.status_code}: {resp.reason}. Resposta: {resp.text}"
                raise HTTPError(error_msg, response=resp) from e


    @staticmethod
    def extract_comp_nfse_list(soap_xml: str) -> list[str]:
        """Retorna uma lista de strings <CompNfse> a partir do SOAP."""
        root = etree.fromstring(soap_xml.encode("utf-8"))
        comps = root.findall(".//{*}CompNfse")
        return [etree.tostring(c, encoding="utf-8").decode("utf-8") for c in comps]