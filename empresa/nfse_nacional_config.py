"""Resolve URL, caminho e senha do PFX: valores da empresa sobrescrevem NFSE_NACIONAL em settings."""
from __future__ import annotations

from typing import Any

from django.conf import settings

from .nfse_nacional_crypto import descriptografar_senha_pfx
from .nfse_nacional_url import normalizar_base_url_sefin


def nfse_nacional_padrao_settings() -> dict[str, Any]:
    return getattr(settings, "NFSE_NACIONAL", {}) or {}


def nfse_nacional_resolvido_para_empresa(empresa) -> dict[str, Any]:
    """
    base_url, pfx_path, pfx_password (texto), verify_ssl.
    Empresa preenchida tem prioridade sobre variáveis de ambiente (via NFSE_NACIONAL).
    """
    d = nfse_nacional_padrao_settings()
    base = (getattr(empresa, "nfse_nacional_base_url", None) or "").strip() or (d.get("base_url") or "")
    base = normalizar_base_url_sefin(base)
    path = ""
    if empresa is not None:
        path = (empresa.nfse_nacional_caminho_pfx() or "").strip()
    if not path:
        path = (d.get("pfx_path") or "")
    senha = ""
    if getattr(empresa, "nfse_nacional_pfx_senha_cifrada", None):
        senha = descriptografar_senha_pfx(empresa.nfse_nacional_pfx_senha_cifrada)
    if not senha:
        senha = d.get("pfx_password") or ""
    verify = d.get("verify_ssl", True)
    if isinstance(verify, str):
        verify = verify.lower() in ("1", "true", "yes")
    return {
        "base_url": base,
        "pfx_path": path,
        "pfx_password": senha,
        "verify_ssl": bool(verify),
        "cert_validade": getattr(empresa, "nfse_nacional_cert_validade", None),
        "thumbprint_sha1": (getattr(empresa, "nfse_nacional_thumbprint_sha1", None) or "").strip(),
    }


def portal_nacional_site_credenciais_para_empresa(empresa) -> dict[str, str]:
    """
    Login/senha do site nfse.gov.br (cadastro da empresa). Senha em texto só para uso controlado no servidor.
    """
    if empresa is None:
        return {"login": "", "senha": ""}
    login = (getattr(empresa, "nfse_portal_nacional_login", None) or "").strip()
    cifr = (getattr(empresa, "nfse_portal_nacional_senha_cifrada", None) or "").strip()
    senha = descriptografar_senha_pfx(cifr).strip() if cifr else ""
    return {"login": login, "senha": senha}
