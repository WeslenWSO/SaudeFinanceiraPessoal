"""Criptografia simples da senha do PFX (Fernet derivado do SECRET_KEY)."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def criptografar_senha_pfx(plain: str) -> str:
    if plain is None or plain == "":
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def descriptografar_senha_pfx(cifrado: str) -> str:
    if not (cifrado or "").strip():
        return ""
    try:
        return _fernet().decrypt(cifrado.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""
