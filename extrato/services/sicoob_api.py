"""
Cliente HTTP para API Conta Corrente Sicoob (extrato).

Conforme documentação de segurança do Sicoob, o OAuth 2.0 usado é **client credentials**
(RFC 6749): o aplicativo autentica com **Client ID** + **certificado digital (mTLS)**,
sem enviar usuário/senha do cooperado no POST do token.

- Padrão: ``SICOOB_TOKEN_GRANT=client_credentials`` (``settings`` / ambiente).
- Legado opcional: ``SICOOB_TOKEN_GRANT=password`` (resource owner / Direct Access Grants),
  exige chave de acesso + senha; muitos apps PF no portal não liberam esse fluxo.

Para teste local opcional: ``SICOOB_ACCESS_TOKEN`` com JWT já emitido (expira rápido).

mTLS: arquivo ``.pfx`` + senha ou par ``.pem`` (cert + chave), nunca só certificado no Windows.

Variáveis: ``SICOOB_CLIENT_ID``, ``SICOOB_CLIENT_SECRET`` (se o app for confidencial),
``SICOOB_TOKEN_URL``, ``SICOOB_API_BASE``, ``SICOOB_SCOPE``, ``SICOOB_MTLS_*``.

Por empresa: ``sicoob_client_id``, ``sicoob_client_secret_cifrada``, ``sicoob_chave_acesso``,
``sicoob_senha_cifrada`` (só fluxo password); ``sicoob_mtls_usar_pfx_nfse`` reutiliza PFX da NFS-e.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, TYPE_CHECKING

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12
from django.conf import settings

if TYPE_CHECKING:
    from empresa.models import Empresa

logger = logging.getLogger(__name__)


def _cfg(name: str, default: str = "") -> str:
    v = getattr(settings, name, None)
    if v is not None and str(v).strip():
        return str(v).strip()
    return default


def _token_grant_mode() -> str:
    """``password`` (legado) ou ``client_credentials`` (padrão documentação Sicoob)."""
    g = (_cfg("SICOOB_TOKEN_GRANT", "client_credentials") or "client_credentials").lower()
    if g in ("password", "resource_owner", "ropc", "direct"):
        return "password"
    return "client_credentials"


def _pfx_para_pem_temporarios(pfx_path: str, pfx_password: str) -> tuple[str, str]:
    """Retorna (cert_pem_path, key_pem_path) temporários; o chamador deve apagar após uso."""
    with open(pfx_path, "rb") as f:
        blob = f.read()
    pwd = pfx_password.encode("utf-8") if pfx_password else None
    key, cert, _chain = pkcs12.load_key_and_certificates(blob, pwd, default_backend())
    if cert is None or key is None:
        raise ValueError("PFX sem certificado ou chave privada (necessário para mTLS Sicoob).")
    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
    cf = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    kf = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    try:
        cf.write(cert_pem)
        kf.write(key_pem)
        cf.flush()
        kf.flush()
        return cf.name, kf.name
    finally:
        cf.close()
        kf.close()


def _resolver_mtls_cert_config(
    empresa: "Empresa | None",
) -> tuple[tuple[str, str] | None, list[str], str | None]:
    """
    Retorna ``(cert_tuple, temp_paths, erro_config)``.
    ``cert_tuple`` é ``(cert_pem_path, key_pem_path)`` para ``requests(..., cert=...)``.
    ``temp_paths`` são arquivos a apagar após a requisição (derivados de PFX).
    """
    from empresa.nfse_nacional_crypto import descriptografar_senha_pfx

    cert_file = _cfg("SICOOB_MTLS_CERT")
    key_file = _cfg("SICOOB_MTLS_KEY")
    if cert_file and key_file and os.path.isfile(cert_file) and os.path.isfile(key_file):
        return (cert_file, key_file), [], None

    pfx_path = ""
    pfx_pw = ""
    env_pfx = (_cfg("SICOOB_MTLS_PFX") or "").strip()
    env_pw = (_cfg("SICOOB_MTLS_PFX_PASSWORD") or "").strip()
    if env_pfx:
        if not env_pw:
            return None, [], "SICOOB_MTLS_PFX exige SICOOB_MTLS_PFX_PASSWORD no servidor."
        if not os.path.isfile(env_pfx):
            return None, [], f"SICOOB_MTLS_PFX inexistente ou inacessível: {env_pfx}"
        pfx_path, pfx_pw = env_pfx, env_pw
    elif empresa is not None and getattr(empresa, "sicoob_mtls_usar_pfx_nfse", False):
        ep = (empresa.nfse_nacional_caminho_pfx() or "").strip()
        cif = getattr(empresa, "nfse_nacional_pfx_senha_cifrada", None) or ""
        pw = descriptografar_senha_pfx(cif).strip() if cif else ""
        if not ep:
            return (
                None,
                [],
                "Marque 'mTLS com o mesmo PFX da NFS-e nacional', mas não há certificado (.pfx) enviado nem caminho no servidor.",
            )
        if not pw:
            return (
                None,
                [],
                "Marque 'mTLS com o mesmo PFX da NFS-e nacional', mas informe e salve a senha do PFX em 'Senha do arquivo .pfx' (NFS-e nacional).",
            )
        if not os.path.isfile(ep):
            return None, [], f"Arquivo PFX da NFS-e não encontrado: {ep}"
        pfx_path, pfx_pw = ep, pw

    if pfx_path and pfx_pw:
        try:
            c, k = _pfx_para_pem_temporarios(pfx_path, pfx_pw)
            return (c, k), [c, k], None
        except Exception as e:
            logger.exception("Sicoob mTLS: falha ao ler PFX")
            return None, [], f"Não foi possível abrir o PFX para mTLS: {e}"

    return None, [], None


def _cleanup_mtls_temp_paths(paths: list[str]) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def _credenciais_token_sicoob(empresa: "Empresa | None" = None) -> tuple[str, str, str, str]:
    """Retorna (client_id, username, password, client_secret) para o POST do token."""
    from empresa.nfse_nacional_crypto import descriptografar_senha_pfx

    client_id = _cfg("SICOOB_CLIENT_ID")
    client_secret = _cfg("SICOOB_CLIENT_SECRET")
    username = _cfg("SICOOB_CHAVE_ACESSO") or _cfg("SICOOB_USERNAME")
    password = _cfg("SICOOB_SENHA") or _cfg("SICOOB_PASSWORD")

    if empresa is not None:
        cid = (getattr(empresa, "sicoob_client_id", None) or "").strip()
        ch = (getattr(empresa, "sicoob_chave_acesso", None) or "").strip()
        sen_cif = getattr(empresa, "sicoob_senha_cifrada", None) or ""
        sec_cif = getattr(empresa, "sicoob_client_secret_cifrada", None) or ""
        sen_pla = descriptografar_senha_pfx(sen_cif).strip() if sen_cif else ""
        sec_pla = descriptografar_senha_pfx(sec_cif).strip() if sec_cif else ""
        if cid:
            client_id = cid
        if ch:
            username = ch
        if sen_pla:
            password = sen_pla
        if sec_pla:
            client_secret = sec_pla

    return client_id, username, password, client_secret


def _detalhe_erro_resposta_token(r: requests.Response) -> str:
    texto = (r.text or "").strip()[:800]
    try:
        body = r.json()
        if isinstance(body, dict):
            msg = (
                body.get("error_description")
                or body.get("errorMessage")
                or body.get("message")
                or body.get("error")
            )
            if msg:
                return str(msg)
    except Exception:
        pass
    return texto or "(resposta sem corpo útil)"


def _hint_token_falha(r: requests.Response, det: str, client_secret: str) -> str:
    dl = det.lower()
    if r.status_code == 400 and (
        "direct access" in dl
        or "direct_access" in dl
        or ("not allowed" in dl and "grant" in dl)
    ):
        return (
            " O Client ID não está liberado para «Direct Access Grants» (grant_type=password no Keycloak). "
            "Peça ao Sicoob/Cooperativa ou consulte o Portal Developers se o tipo de app (ex. PF) permite esse fluxo "
            "ou se a integração deve usar outro método (ex.: Authorization Code no navegador). "
            "Para testar só o extrato localmente, defina SICOOB_ACCESS_TOKEN com um access_token JWT válido "
            "(cópia temporária; expira em poucos minutos)."
        )
    if r.status_code in (401, 403) and (
        "certificado" in dl or "digital" in dl or "mtls" in dl or "tls" in dl
    ):
        return (
            " Este recurso exige certificado cliente na conexão HTTPS (mTLS): defina no servidor "
            "SICOOB_MTLS_CERT + SICOOB_MTLS_KEY, ou SICOOB_MTLS_PFX + SICOOB_MTLS_PFX_PASSWORD, "
            "ou marque na empresa 'Sicoob — mTLS com o mesmo PFX da NFS-e nacional' e mantenha "
            "caminho + senha do PFX da NFS-e. Certificado apenas instalado no Windows não é usado pelo Python."
        )
    if r.status_code in (401, 403) and not client_secret:
        return (
            " Inclua o Client Secret do Dashboard do Portal Developers "
            "(campo na empresa ou variável SICOOB_CLIENT_SECRET no servidor)."
        )
    return ""


def obter_access_token_sicoob(empresa: "Empresa | None" = None) -> str:
    """
    Obtém access_token no endpoint OpenID do Sicoob.

    Modo padrão: ``client_credentials`` + mTLS + Client ID (documentação Sicoob).
    Modo legado: ``SICOOB_TOKEN_GRANT=password`` + usuário/senha cooperado.

    Se ``SICOOB_ACCESS_TOKEN`` estiver definido, devolve esse valor (só depuração).
    """
    bypass = _cfg("SICOOB_ACCESS_TOKEN")
    if bypass:
        logger.warning(
            "Sicoob token: usando SICOOB_ACCESS_TOKEN (bypass; não chama o endpoint de token; expira como qualquer JWT)."
        )
        return bypass.strip()

    grant = _token_grant_mode()
    client_id, username, password, client_secret = _credenciais_token_sicoob(empresa)

    if grant == "password":
    if not client_id or not username or not password:
            raise ValueError(
                "Configure credenciais Sicoob (fluxo password): Client ID, chave de acesso/usuário e senha "
                "na empresa ou SICOOB_CLIENT_ID + SICOOB_CHAVE_ACESSO/SICOOB_USERNAME + senha no servidor."
            )
    else:
        if not client_id:
            raise ValueError(
                "Configure o Client ID Sicoob (empresa ou SICOOB_CLIENT_ID). "
                "No fluxo client credentials (padrão) não se usa usuário/senha do cooperado no token."
            )

    cert_tuple, temp_paths, mtls_err = _resolver_mtls_cert_config(empresa)
    if mtls_err:
        raise ValueError(mtls_err)
    if grant == "client_credentials" and not cert_tuple:
        raise ValueError(
            "Fluxo OAuth client credentials (padrão Sicoob): é obrigatório certificado cliente (mTLS) "
            "na requisição do token. Defina SICOOB_MTLS_CERT+KEY ou SICOOB_MTLS_PFX+senha, ou marque na empresa "
            "«Sicoob — mTLS com o mesmo PFX da NFS-e nacional» com caminho e senha do PFX."
        )

    token_url = _cfg(
        "SICOOB_TOKEN_URL",
        "https://auth.sicoob.com.br/auth/realms/cooperado/protocol/openid-connect/token",
    )
    scope = _cfg("SICOOB_SCOPE", "openid cco_extrato")
    if grant == "client_credentials":
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "scope": scope,
        }
        if client_secret:
            data["client_secret"] = client_secret
    else:
    data = {
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
        "scope": scope,
    }
        if client_secret:
            data["client_secret"] = client_secret
    try:
    r = requests.post(
        token_url,
        data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "SaudeFinanceira/1.0 (Sicoob OAuth2 token)",
            },
            cert=cert_tuple,
        timeout=60,
    )
    finally:
        _cleanup_mtls_temp_paths(temp_paths)

    if r.status_code != 200:
        det = _detalhe_erro_resposta_token(r)
        logger.warning("Sicoob token HTTP %s: %s", r.status_code, det[:500])
        hint = _hint_token_falha(r, det, client_secret)
        raise ValueError(f"Falha ao obter token Sicoob (HTTP {r.status_code}). {det}{hint}")
    body = r.json()
    token = body.get("access_token")
    if not token:
        raise ValueError("Resposta do token Sicoob sem access_token.")
    return str(token)


def consultar_extrato_sicoob(
    mes: int,
    ano: int,
    numero_conta_corrente: int | str,
    *,
    dia_inicial: int | None = None,
    dia_final: int | None = None,
    agrupar_cnab: bool | None = None,
    access_token: str | None = None,
    empresa: "Empresa | None" = None,
) -> dict[str, Any]:
    """
    GET {SICOOB_API_BASE}/extrato/{mes}/{ano}
    Header: client_id (obrigatório na API Sicoob) + Authorization Bearer.
    Query: numeroContaCorrente (obrigatório).
    """
    client_id, _, _, _ = _credenciais_token_sicoob(empresa)
    if not client_id:
        raise ValueError("Sicoob Client ID não configurado (empresa ou SICOOB_CLIENT_ID no servidor).")
    base = _cfg("SICOOB_API_BASE", "https://api.sicoob.com.br/conta-corrente/v4").rstrip("/")
    url = f"{base}/extrato/{int(mes)}/{int(ano)}"
    params: dict[str, Any] = {"numeroContaCorrente": int(numero_conta_corrente)}
    if dia_inicial is not None:
        params["diaInicial"] = int(dia_inicial)
    if dia_final is not None:
        params["diaFinal"] = int(dia_final)
    if agrupar_cnab is not None:
        params["agruparCNAB"] = bool(agrupar_cnab)

    cert_tuple, temp_paths, mtls_err = _resolver_mtls_cert_config(empresa)
    if mtls_err:
        raise ValueError(mtls_err)

    try:
        token = access_token or obter_access_token_sicoob(empresa)
    headers = {
        "client_id": client_id,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
        r = requests.get(url, headers=headers, params=params, cert=cert_tuple, timeout=120)
    finally:
        _cleanup_mtls_temp_paths(temp_paths)

    if r.status_code != 200:
        logger.warning("Sicoob extrato HTTP %s: %s", r.status_code, r.text[:800])
        msg = (r.text or "").strip()[:500]
        cod: str | None = None
        try:
            err = r.json()
            if isinstance(err, dict):
                msg = (
                    err.get("moreInformation")
                    or err.get("httpMessage")
                    or err.get("mensagem")
                    or err.get("message")
                    or msg
                )
                cod = str(err.get("httpCode") or err.get("codigo") or err.get("code") or "") or None
        except Exception:
            pass
        extra = ""
        if r.status_code == 401:
            extra = (
                " — O gateway rejeitou a combinação token + client_id + URL/certificado. "
                "Confira: (1) o header «client_id» deve ser o **mesmo Client ID** do aplicativo que emitiu o Bearer "
                "(token do **Sandbox** do portal exige o Client ID de sandbox, não o da produção); "
                "(2) **SICOOB_API_BASE** deve ser a URL de **homologação** ao usar token/credenciais de sandbox "
                "(a de produção `api.sicoob.com.br` costuma recusar token de teste); "
                "(3) token OAuth expira em poucos minutos; token fixo do sandbox, renove no portal se mudar; "
                "(4) em **produção**, mTLS com o certificado do app costuma ser obrigatório também neste GET."
            )
        raise ValueError(
            f"API Sicoob (HTTP {r.status_code}): {msg}" + (f" [código {cod}]" if cod else "") + extra
        )
    return r.json()
