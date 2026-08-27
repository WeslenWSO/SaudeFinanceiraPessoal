"""Evita importar recebíveis duplicados (autorização + data pagamento + parcela + máquina)."""

from __future__ import annotations

import re

from .models import RelatorioRecebiveisMaquinaCartao


def parcela_chave(parcelas, total_parcelas, parcela_texto=None) -> str:
    """Chave normalizada da parcela (ex.: 1/3)."""
    txt = (parcela_texto or '').strip()
    if txt:
        m = re.search(r'(\d+)\s*/\s*(\d+)', txt)
        if m:
            return f'{int(m.group(1))}/{int(m.group(2))}'
        if txt.isdigit():
            return f'{int(txt)}/1'
        return txt.lower()
    p = int(parcelas or 1)
    t = int(total_parcelas or p)
    return f'{p}/{t}'


def dedup_key(relatorio) -> tuple | None:
    """
    Tupla (autorização, data_pagamento, parcela, máquina) ou None se não deduplicável.
    Exige autorização e data de pagamento preenchidos.
    """
    auth = (relatorio.numero_autorizacao or '').strip()
    if not auth or not relatorio.data_pagamento:
        return None
    maq = (relatorio.maquinha or '').strip().upper()
    parcela = parcela_chave(
        relatorio.parcelas,
        relatorio.total_parcelas,
        relatorio.parcela_texto,
    )
    return (auth, relatorio.data_pagamento, parcela, maq)


def existe_duplicado(empresa_id, key: tuple) -> bool:
    auth, data_pag, parcela, maq = key
    candidatos = RelatorioRecebiveisMaquinaCartao.objects.filter(
        empresa_id=empresa_id,
        numero_autorizacao=auth,
        data_pagamento=data_pag,
    ).only('parcelas', 'total_parcelas', 'parcela_texto', 'maquinha')

    for existente in candidatos:
        if (existente.maquinha or '').strip().upper() != maq:
            continue
        if parcela_chave(
            existente.parcelas,
            existente.total_parcelas,
            existente.parcela_texto,
        ) == parcela:
            return True
    return False


class RecebivelImportDedup:
    """Controla duplicatas no banco e dentro do mesmo arquivo de importação."""

    def __init__(self, empresa_id):
        self.empresa_id = empresa_id
        self._batch_keys: set[tuple] = set()
        self.duplicate_count = 0

    def salvar(self, relatorio) -> bool:
        """
        Salva o recebível se não for duplicata.
        Retorna True se gravou, False se ignorou por duplicidade.
        """
        key = dedup_key(relatorio)
        if key is None:
            relatorio.save()
            return True

        if key in self._batch_keys or existe_duplicado(self.empresa_id, key):
            self.duplicate_count += 1
            self._batch_keys.add(key)
            return False

        relatorio.save()
        self._batch_keys.add(key)
        return True
