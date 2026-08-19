"""Helpers de identificação de procedimentos."""

from __future__ import annotations

import re

_TRANSVAGINAL_RE = re.compile(r'transvag', re.IGNORECASE)


def eh_procedimento_transvaginal(procedimento: str | None) -> bool:
    return bool(_TRANSVAGINAL_RE.search(procedimento or ''))
