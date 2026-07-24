"""Leitura de metadados do certificado em arquivo PFX (PKCS#12)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12


def extrair_validade_pfx_bytes(data: bytes, password: str) -> date | None:
    """
    Retorna a data de fim de validade a partir do conteúdo PKCS#12 (upload ou memória).
    """
    if not data or not password:
        return None
    pwd = password.encode("utf-8") if isinstance(password, str) else password
    try:
        _key, cert, _chain = pkcs12.load_key_and_certificates(data, pwd, default_backend())
    except Exception:
        return None
    if cert is None:
        return None
    na = getattr(cert, "not_valid_after_utc", None) or getattr(cert, "not_valid_after", None)
    if na is None:
        return None
    if isinstance(na, datetime):
        if na.tzinfo is not None:
            na = na.astimezone(timezone.utc).replace(tzinfo=None)
        return na.date()
    return None


def extrair_validade_pfx(pfx_path: str, password: str) -> date | None:
    """
    Retorna a data de fim de validade do certificado (não a chave privada).
    """
    if not pfx_path or not password:
        return None
    path = Path(pfx_path)
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return extrair_validade_pfx_bytes(data, password)
