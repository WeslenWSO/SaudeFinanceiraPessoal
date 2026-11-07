"""Indicador NFSe × contas a receber (vínculo FK ou título CA pelo doc)."""
from __future__ import annotations

from django.db.models import Q

from contasareceber.nf_sync_discriminacao import _digitos_nf, _variantes_numero_nf

# fk = CAR com nota_id; ca = título CA localizado pelo número/doc, sem FK obrigatória
CAR_NFSE_FK = 'fk'
CAR_NFSE_CA = 'ca'


def status_car_nfse_listagem(empresa_id: int, notas) -> dict[int, str]:
    """
    Para cada NF da página, retorna como o CAR foi localizado:
    - fk: ContaAReceber.nota_id aponta para a NF
    - ca: título vindo do Conta Azul (doc = nº da nota ou parcela CA), ainda sem FK
    - '': nenhum CAR encontrado
    """
    from contasareceber.models import ContaAReceber

    notas_list = list(notas)
    if not empresa_id or not notas_list:
        return {}

    ids = [n.id for n in notas_list if getattr(n, 'id', None)]
    out: dict[int, str] = {i: '' for i in ids}

    for nid in (
        ContaAReceber.objects.filter(empresa_id=empresa_id, nota_id__in=ids)
        .values_list('nota_id', flat=True)
        .distinct()
    ):
        if nid in out:
            out[nid] = CAR_NFSE_FK

    pendentes = [n for n in notas_list if n.id in out and not out[n.id]]
    if not pendentes:
        return out

    chaves_doc: set[str] = set()
    dig_por_nf: dict[int, str] = {}
    for n in pendentes:
        dig_por_nf[n.id] = _digitos_nf(n.numero_nota or '')
        chaves_doc.update(_variantes_numero_nf(n.numero_nota or ''))

    q_doc = Q()
    if chaves_doc:
        q_doc |= Q(doc__in=list(chaves_doc))
    q_doc |= Q(conta_azul_parcela_id__gt='')

    cars = (
        ContaAReceber.objects.filter(empresa_id=empresa_id, nota_id__isnull=True)
        .filter(q_doc)
        .only('pk', 'doc', 'conta_azul_parcela_id')
    )

    for car in cars:
        doc_bruto = (car.doc or '').strip()
        doc_dig = _digitos_nf(doc_bruto)
        tem_ca = bool((car.conta_azul_parcela_id or '').strip())
        for n in pendentes:
            if out[n.id]:
                continue
            num_vars = set(_variantes_numero_nf(n.numero_nota or ''))
            if doc_bruto and doc_bruto in num_vars:
                out[n.id] = CAR_NFSE_CA
                continue
            nd = dig_por_nf.get(n.id) or ''
            if nd and doc_dig and nd == doc_dig:
                out[n.id] = CAR_NFSE_CA
                continue
            if tem_ca and doc_bruto and nd and doc_bruto == n.numero_nota.strip():
                out[n.id] = CAR_NFSE_CA

    return out


def nota_ids_com_car_resolvido(status: dict[int, str]) -> set[int]:
    return {nid for nid, st in status.items() if st in (CAR_NFSE_FK, CAR_NFSE_CA)}
