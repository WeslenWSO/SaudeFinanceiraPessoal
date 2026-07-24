# nfse_rio_branco/services/abrasf_parser.py
from __future__ import annotations
from lxml import etree
from datetime import datetime
from dateutil import parser as dateparser


NS = {
    "nfse": "http://www.abrasf.org.br/nfse.xsd",
}


class AbrasfParseError(Exception):
    pass


def _text(node, xpath: str):
    el = node.find(xpath, namespaces=NS)
    return el.text.strip() if el is not None and el.text else None


def parse_compnfse(xml_str: str) -> dict:
    """Recebe um XML ABRASF contendo <CompNfse> e retorna um dicionário normalizado."""
    try:
        root = etree.fromstring(xml_str.encode("utf-8"))
    except Exception as e:
        raise AbrasfParseError(f"XML inválido: {e}")


    # Suporte a envelopes diferentes: <CompNfse>, <ListaNfse>, etc.
    comp = root
    if root.tag.endswith("ListaNfse"):
        comp = root.find(".//{*}CompNfse")
    elif not root.tag.endswith("CompNfse"):
        comp = root.find(".//{*}CompNfse")


    if comp is None:
       raise AbrasfParseError("Elemento <CompNfse> não encontrado.")


    nfse = comp.find(".//{*}Nfse/{*}InfNfse")
    if nfse is None:
         raise AbrasfParseError("Elemento <InfNfse> não encontrado.")


    numero = _text(nfse, ".//{*}Numero")
    codigo_verificacao = _text(nfse, ".//{*}CodigoVerificacao")
    data_emissao_raw = _text(nfse, ".//{*}DataEmissao")
    data_emissao = dateparser.parse(data_emissao_raw) if data_emissao_raw else None
    competencia = _text(nfse, ".//{*}Competencia")
    valor_servico = _text(nfse, ".//{*}Servico/{*}Valores/{*}ValorServicos")
    iss_retido = _text(nfse, ".//{*}Servico/{*}IssRetido") in ("1", "true", "True")
    prestador_cnpj = _text(nfse, ".//{*}PrestadorServico/{*}IdentificacaoPrestador/{*}Cnpj")
    tomador_doc = _text(nfse, ".//{*}TomadorServico/{*}IdentificacaoTomador/{*}CpfCnpj/{*}Cnpj") or \
                  _text(nfse, ".//{*}TomadorServico/{*}IdentificacaoTomador/{*}CpfCnpj/{*}Cpf")


    return {
          "numero": numero,
          "codigo_verificacao": codigo_verificacao,
          "data_emissao": data_emissao,
          "competencia": competencia,
          "valor_servico": valor_servico,
          "iss_retido": iss_retido,
          "prestador_cnpj": prestador_cnpj,
          "tomador_cnpj_cpf": tomador_doc,
    }