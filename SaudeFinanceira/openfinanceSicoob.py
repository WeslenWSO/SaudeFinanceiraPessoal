"""
Script / utilitário: token OAuth + GET extrato Sicoob (client_credentials + mTLS).

Origem dos dados (alinhado ao cadastro no sistema):
  - Client ID: campo ``sicoob_client_id`` da empresa (ou ``SICOOB_CLIENT_ID`` no ambiente).
  - Senha do cooperado: ``sicoob_chave_acesso`` + ``sicoob_senha_cifrada`` — usada só no fluxo
    legado ``grant_type=password`` (se habilitado no Keycloak). O fluxo padrão documentado
    pelo Sicoob é **client_credentials** e **não** envia usuário/senha cooperado no POST do token.
  - Certificado: arquivo enviado no cadastro ou caminho absoluto no servidor (``Empresa.nfse_nacional_caminho_pfx()``).
    PEMs auxiliares são gravados na **mesma pasta** do arquivo .pfx (ou pasta informada).
  - Nº conta API: ``sicoob_numero_conta_corrente_api`` na ``ContaBancaria``.
  - mês/ano: parâmetros da tela de importação de extrato ou deste script.

Uso:
  - Pelo Django (recomendado): ``python manage.py shell`` e importar ``executar_de_empresa_conta``.
  - Em linha de comando: ``python SaudeFinanceira/openfinanceSicoob.py <empresa_id> <conta_id> <mês> <ano>``
    (com ``DJANGO_SETTINGS_MODULE=SaudeFinanceira.settings``).

A importação na tela de lançamentos chama ``executar_de_empresa_conta`` via ``extrato.services.sicoob_import``.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import sys
import requests
from requests.adapters import HTTPAdapter
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives.serialization import pkcs12 as crypto_pkcs12

logger = logging.getLogger(__name__)


def mascarar_senha_pfx(senha: str | None) -> str:
    """Log seguro: não gravar senha do PFX em claro."""
    if not senha:
        return "(vazia)"
    n = len(senha)
    if n <= 2:
        return f"*** (len={n})"
    return f"{senha[0]}…{senha[-1]} (len={n})"


def mascarar_token_oauth(token: str | None) -> str:
    """Log seguro do access_token (Bearer)."""
    if not token:
        return "(não obtido)"
    n = len(token)
    if n <= 24:
        return f"*** (len={n})"
    return f"{token[:10]}…{token[-8:]} (len={n})"


def _deve_logar_json_extrato() -> bool:
    try:
        from django.conf import settings

        return bool(getattr(settings, "SICOOB_LOG_EXTRATO_JSON", True))
    except Exception:
        return True


def log_resposta_extrato_json_no_console(corpo: Any, prefixo: str = "Sicoob extrato resposta") -> None:
    """Registra o JSON retornado pela API (várias linhas se for grande)."""
    if not _deve_logar_json_extrato():
        return
    try:
        texto = json.dumps(corpo, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        texto = repr(corpo)
    limite = 14000
    total = max(1, (len(texto) + limite - 1) // limite)
    for i in range(total):
        bloco = texto[i * limite : (i + 1) * limite]
        logger.info("%s JSON [%s/%s]:\n%s", prefixo, i + 1, total, bloco)


class SSLAdapter(HTTPAdapter):
    """Transport HTTPS com contexto SSL (mTLS)."""

    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)


def extrair_pem_do_pfx(
    pfx_path: str,
    password: str,
    pasta_saida: str | None = None,
) -> tuple[str, str] | None:
    """
    Lê o PFX e grava ``<base>_cert.pem`` e ``<base>_chave.pem`` (com cadeia no cert, se houver).
    """
    if not os.path.isfile(pfx_path):
        logger.warning("PFX não encontrado: %s", pfx_path)
        return None
    pasta = pasta_saida or os.path.dirname(os.path.abspath(pfx_path)) or "."
    base = os.path.splitext(os.path.basename(pfx_path))[0]
    cert_out = os.path.join(pasta, f"{base}_cert.pem")
    key_out = os.path.join(pasta, f"{base}_chave.pem")

    try:
        with open(pfx_path, "rb") as f:
            pfx_data = f.read()
        pwd = password.encode("utf-8") if isinstance(password, str) else password
        private_key, certificate, cadeia_adicional = crypto_pkcs12.load_key_and_certificates(pfx_data, pwd)
        if private_key is None or certificate is None:
            logger.warning("PFX sem chave privada ou certificado.")
            return None

        cert_pem = certificate.public_bytes(Encoding.PEM)
        key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        with open(cert_out, "wb") as f:
            f.write(cert_pem)
            if cadeia_adicional:
                for extra in cadeia_adicional:
                    if extra is not None:
                        f.write(extra.public_bytes(Encoding.PEM))
        with open(key_out, "wb") as f:
            f.write(key_pem)

        logger.info(
            "Sicoob mTLS: PEM extraídos do PFX | cert_pem=%s | key_pem=%s",
            cert_out,
            key_out,
        )
        return cert_out, key_out
    except Exception as e:
        logger.warning("Erro ao extrair PEM do PFX (senha incorreta ou arquivo inválido): %s", e)
        return None


def criar_contexto_ssl(cert_path: str, key_path: str):
    try:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.load_cert_chain(cert_path, key_path)
    except Exception as e:
        logger.error("Erro SSL ao carregar certificado cliente: %s", e)
        return None
    return ssl_context


def montar_corpo_token(client_id: str, scope: str, client_secret: str | None = None) -> dict[str, str]:
    corpo: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "scope": scope,
    }
    if client_secret:
        corpo["client_secret"] = client_secret
    return corpo


def gerar_token(session: requests.Session, url_token: str, data: dict, headers: dict) -> str | None:
    try:
        response = session.post(url_token, data=data, headers=headers, timeout=60)
        if response.status_code == 200:
            tok = response.json().get("access_token")
            logger.info(
                "Sicoob OAuth POST token OK | url=%s | token=%s",
                url_token,
                mascarar_token_oauth(tok if isinstance(tok, str) else None),
            )
            return tok
        logger.warning(
            "Sicoob OAuth POST token falhou | url=%s | status=%s | body=%s",
            url_token,
            response.status_code,
            (response.text or "")[:1200],
        )
        return None
    except requests.exceptions.SSLError as e:
        logger.error("Sicoob OAuth SSL error | url=%s | erro=%s", url_token, e)
        return None
    except requests.exceptions.RequestException as e:
        logger.exception("Sicoob OAuth request error | url=%s", url_token)
        return None


def consultar_extrato(
    session: requests.Session,
    base_api_url: str,
    access_token: str,
    client_id: str,
    mes: int,
    ano: int,
    numero_conta_corrente: str,
    versao_cco: str = "v4",
    dia_inicial: int | None = None,
    dia_final: int | None = None,
    agrupar_cnab: bool | None = None,
) -> dict[str, Any] | None:
    """GET conta-corrente/{versao}/extrato/{mes}/{ano}."""
    ver = versao_cco.strip().lstrip("/") or "v4"
    url = f"{base_api_url.rstrip('/')}/conta-corrente/{ver}/extrato/{mes}/{ano}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "client_id": client_id,
    }
    nc = "".join(ch for ch in str(numero_conta_corrente) if ch.isdigit())
    params: dict[str, Any] = {"numeroContaCorrente": int(nc) if nc else numero_conta_corrente}
    if dia_inicial is not None:
        params["diaInicial"] = dia_inicial
    if dia_final is not None:
        params["diaFinal"] = dia_final
    if agrupar_cnab is not None:
        params["agruparCNAB"] = agrupar_cnab
    logger.info(
        "Sicoob GET extrato request | mes=%s ano=%s conta=%s dia_inicial=%s dia_final=%s client_id=%s | url=%s | params=%s | token=%s",
        mes,
        ano,
        numero_conta_corrente,
        dia_inicial,
        dia_final,
        client_id,
        url,
        params,
        mascarar_token_oauth(access_token),
    )
    try:
        response = session.get(url, headers=headers, params=params, timeout=120)
        if response.status_code == 200:
            body = response.json()
            txs = body.get("transacoes") or body.get("Transacoes") or []
            n_tx = len(txs) if isinstance(txs, list) else "?"
            logger.info(
                "Sicoob GET extrato OK | url_final=%s | chaves_json=%s | transacoes=%s",
                response.url,
                list(body.keys()) if isinstance(body, dict) else type(body).__name__,
                n_tx,
            )
            log_resposta_extrato_json_no_console(body)
            return body
        logger.warning(
            "Sicoob GET extrato falhou | status=%s | url=%s | body=%s",
            response.status_code,
            response.url,
            (response.text or "")[:1200],
        )
        return None
    except requests.exceptions.SSLError as e:
        logger.error("Sicoob GET extrato SSL: %s", e)
        return None
    except requests.exceptions.RequestException as e:
        logger.exception("Sicoob GET extrato request error | url=%s", url)
        return None


def _django_setup():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
    import django

    django.setup()


def carregar_credenciais_empresa(empresa_pk: int, conta_pk: int) -> dict[str, Any]:
    """
    Lê Empresa + ContaBancaria do banco (mesmos campos do formulário de empresa / conta).
    Retorna dict com client_id, pastas, senhas, número da conta API, URLs e scope.
    """
    _django_setup()
    from empresa.models import Empresa
    from extrato.models import ContaBancaria
    from empresa.nfse_nacional_crypto import descriptografar_senha_pfx

    emp = Empresa.objects.get(pk=empresa_pk)
    conta = ContaBancaria.objects.get(pk=conta_pk, empresa_id=empresa_pk)

    pfx = (emp.nfse_nacional_caminho_pfx() or "").strip()
    if not pfx:
        raise ValueError(
            "Envie o certificado (.pfx) em Empresa ou informe o caminho absoluto no servidor (NFS-e nacional)."
        )
    if not os.path.isfile(pfx):
        raise ValueError(f"Arquivo PFX não encontrado: {pfx}")

    senha_pfx = descriptografar_senha_pfx(emp.nfse_nacional_pfx_senha_cifrada or "").strip()
    if not senha_pfx:
        raise ValueError("Informe e salve a senha do PFX no cadastro da empresa (NFS-e nacional).")

    cid = (emp.sicoob_client_id or "").strip()
    if not cid:
        cid = (os.environ.get("SICOOB_CLIENT_ID") or "").strip()
    if not cid:
        raise ValueError("Preencha Sicoob — Client ID na empresa ou defina SICOOB_CLIENT_ID no servidor.")

    sec_cif = getattr(emp, "sicoob_client_secret_cifrada", None) or ""
    client_secret = descriptografar_senha_pfx(sec_cif).strip() if sec_cif else ""
    if not client_secret:
        client_secret = (os.environ.get("SICOOB_CLIENT_SECRET") or "").strip() or None
    else:
        client_secret = client_secret or None

    num_cc = (conta.sicoob_numero_conta_corrente_api or "").strip()
    if not num_cc:
        raise ValueError("Preencha na conta bancária o campo Sicoob — Nº conta API (extrato).")
    num_cc = "".join(c for c in num_cc if c.isdigit()) or num_cc

    # Senha/usuário cooperado (cadastro API Sicoob) — informativo; fluxo client_credentials não usa no POST do token.
    cooperado_usuario = (emp.sicoob_chave_acesso or "").strip()
    cooperado_senha = (
        descriptografar_senha_pfx(emp.sicoob_senha_cifrada).strip() if emp.sicoob_senha_cifrada else ""
    )

    pasta_cert = os.path.dirname(os.path.abspath(pfx))

    url_token = (os.environ.get("SICOOB_TOKEN_URL") or "").strip() or (
        "https://auth.sicoob.com.br/auth/realms/cooperado/protocol/openid-connect/token"
    )
    url_api = (os.environ.get("SICOOB_API_BASE") or "").strip() or "https://api.sicoob.com.br"
    scope = (os.environ.get("SICOOB_SCOPE") or "").strip() or "cco_extrato cco_saldo cco_consulta"

    return {
        "client_id": cid,
        "client_secret": client_secret,
        "pfx_path": pfx,
        "pfx_password": senha_pfx,
        "pasta_cert": pasta_cert,
        "numero_conta_corrente": num_cc,
        "cooperado_usuario": cooperado_usuario,
        "cooperado_senha": cooperado_senha,
        "url_token": url_token,
        "url_api": url_api,
        "scope": scope,
        "versao_cco": (os.environ.get("SICOOB_CCO_VERSION") or "v4").strip(),
    }


def montar_sessao_mtls(pfx_path: str, pfx_password: str, pasta_saida_pem: str | None = None) -> requests.Session:
    pasta = pasta_saida_pem or os.path.dirname(os.path.abspath(pfx_path))
    pems = extrair_pem_do_pfx(pfx_path, pfx_password, pasta_saida=pasta)
    if not pems:
        raise RuntimeError("Falha ao extrair PEM do PFX.")
    ssl_context = criar_contexto_ssl(pems[0], pems[1])
    if ssl_context is None:
        raise RuntimeError("Falha ao criar SSLContext.")
    session = requests.Session()
    session.mount("https://", SSLAdapter(ssl_context))
    return session


def executar_de_empresa_conta(
    empresa_pk: int,
    conta_pk: int,
    mes: int,
    ano: int,
    *,
    dia_inicial: int | None = None,
    dia_final: int | None = None,
) -> dict[str, Any] | None:
    """
    Obtém token e consulta extrato usando apenas dados de ``Empresa`` + ``ContaBancaria``.
    """
    cfg = carregar_credenciais_empresa(empresa_pk, conta_pk)
    logger.info(
        "Sicoob openfinance | empresa_pk=%s conta_pk=%s | mes=%s ano=%s dia_inicial=%s dia_final=%s | "
        "caminho_pfx=%s | senha_pfx=%s | client_id=%s | conta_api=%s | "
        "url_token=%s | url_api=%s | scope=%s | versao_cco=%s",
        empresa_pk,
        conta_pk,
        mes,
        ano,
        dia_inicial,
        dia_final,
        cfg["pfx_path"],
        mascarar_senha_pfx(cfg["pfx_password"]),
        cfg["client_id"],
        cfg["numero_conta_corrente"],
        cfg["url_token"],
        cfg["url_api"],
        cfg["scope"],
        cfg["versao_cco"],
    )
    session = montar_sessao_mtls(cfg["pfx_path"], cfg["pfx_password"], pasta_saida_pem=cfg["pasta_cert"])
    data = montar_corpo_token(cfg["client_id"], cfg["scope"], cfg["client_secret"])
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    token = gerar_token(session, cfg["url_token"], data, headers)
    logger.info("Sicoob openfinance | token=%s", mascarar_token_oauth(token))
    if not token:
        logger.error(
            "Sicoob openfinance | OAuth sem access_token; confira certificado mTLS, Client ID/Secret e ambiente (homologação x produção)."
        )
        return None
    out = consultar_extrato(
        session,
        cfg["url_api"],
        token,
        cfg["client_id"],
        mes,
        ano,
        cfg["numero_conta_corrente"],
        versao_cco=cfg["versao_cco"],
        dia_inicial=dia_inicial,
        dia_final=dia_final,
    )
    if out is None:
        logger.error("Sicoob openfinance | GET extrato retornou None (ver WARNING acima da API).")
    else:
        txs = out.get("transacoes") or out.get("Transacoes") or []
        n = len(txs) if isinstance(txs, list) else "?"
        logger.info("Sicoob openfinance | extrato JSON recebido | transacoes=%s", n)
    return out


if __name__ == "__main__":
    # Ex.: python openfinanceSicoob.py 11 3 12 2025
    if len(sys.argv) >= 5:
        emp_id, conta_id, mes_i, ano_i = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
        print(f"Empresa={emp_id}, Conta={conta_id}, mês={mes_i}, ano={ano_i}")
        ext = executar_de_empresa_conta(emp_id, conta_id, mes_i, ano_i)
        if ext is not None:
            print("Extrato:", ext)
        sys.exit(0 if ext is not None else 1)

    # Fallback sem ORM: variáveis de ambiente (sem senhas no código)
    print(
        "Uso: python openfinanceSicoob.py <empresa_id> <conta_id> <mes> <ano>\n"
        "  Ou configure PFX_PATH, PFX_PASSWORD, SICOOB_CLIENT_ID e rode com variáveis de ambiente."
    )
    pfx_path = os.environ.get("PFX_PATH", "").strip()
    pfx_pw = os.environ.get("PFX_PASSWORD", "").strip()
    if not pfx_path or not pfx_pw:
        sys.exit(1)

    client_id = os.environ.get("SICOOB_CLIENT_ID", "").strip()
    if not client_id:
        print("Defina SICOOB_CLIENT_ID")
        sys.exit(1)

    mes = int(os.environ.get("MES", "12"))
    ano = int(os.environ.get("ANO", "2025"))
    numero_cc = os.environ.get("NUMERO_CC", "").strip()
    url_token = os.environ.get(
        "SICOOB_TOKEN_URL",
        "https://auth.sicoob.com.br/auth/realms/cooperado/protocol/openid-connect/token",
    )
    url_api = os.environ.get("SICOOB_API_BASE", "https://api.sicoob.com.br")
    scope = os.environ.get("SICOOB_SCOPE", "cco_extrato cco_saldo cco_consulta")
    client_secret = (os.environ.get("SICOOB_CLIENT_SECRET") or "").strip() or None
    pasta = os.environ.get("PASTA_CERT", "").strip() or os.path.dirname(os.path.abspath(pfx_path))

    session = montar_sessao_mtls(pfx_path, pfx_password=pfx_pw, pasta_saida_pem=pasta)
    data = montar_corpo_token(client_id, scope, client_secret)
    token = gerar_token(session, url_token, data, {"Content-Type": "application/x-www-form-urlencoded"})
    if token and numero_cc:
        ext = consultar_extrato(
            session, url_api, token, client_id, mes, ano, numero_cc
        )
        print(ext)
    sys.exit(0 if token else 1)
