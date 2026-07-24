"""Utilitários de URL da SEFIN (sem dependência de models/settings)."""

from __future__ import annotations



import re





def normalizar_base_url_sefin(base_url: str) -> str:

    """

    Extrai uma URL http(s) usável pelo requests.

    Corrige colagens do tipo ': https://sefin...' que geram

    "No connection adapters were found for ...".

    """

    s = (base_url or "").strip().strip("'\"")

    if not s:

        return ""

    m = re.search(r"https?://[^\s\"'<>\]]+", s, re.I)

    if m:

        return m.group(0).rstrip("/").rstrip("'\",);")

    return s.rstrip("/")


