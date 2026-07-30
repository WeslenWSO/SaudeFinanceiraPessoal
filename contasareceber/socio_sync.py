"""Sincronização entre NFSe e contas a receber (parcelas).

`QuerySet.update()` em NotaFiscalServico não dispara `save()`; use
`propagar_socio_para_contas_das_notas` / `propagar_forma_pagamento_para_contas_das_notas`
nesses casos.
"""


def propagar_socio_nota_para_contas_receber(nota):
    """Alinha o sócio em todas as parcelas (CAR) com a NF já salva (mesmo `nota_id`)."""
    from .models import ContaAReceber

    if not nota or not getattr(nota, "pk", None):
        return 0
    return ContaAReceber.objects.filter(nota_id=nota.pk).update(socio_id=nota.socio_id)


def propagar_socio_para_contas_das_notas(nota_ids, socio_id):
    """Define o mesmo sócio em todas as contas a receber vinculadas às notas."""
    from .models import ContaAReceber

    if not nota_ids:
        return 0
    return ContaAReceber.objects.filter(nota_id__in=nota_ids).update(socio_id=socio_id)


def propagar_forma_pagamento_nota_para_contas_receber(nota):
    """Alinha cobrança (forma de pagamento) nas parcelas CAR com a NF já salva."""
    from .models import ContaAReceber

    if not nota or not getattr(nota, "pk", None):
        return 0
    fp_id = getattr(nota, "forma_pagamento_id", None)
    return ContaAReceber.objects.filter(nota_id=nota.pk).update(forma_pagamento_id=fp_id)


def propagar_forma_pagamento_para_contas_das_notas(nota_ids, forma_pagamento_id):
    """Define a mesma cobrança em todas as CAR vinculadas às notas (ex.: bulk em NF)."""
    from .models import ContaAReceber

    if not nota_ids:
        return 0
    return ContaAReceber.objects.filter(nota_id__in=nota_ids).update(
        forma_pagamento_id=forma_pagamento_id
    )


def _autorizacao_da_nota(nota):
    """Autorização do cartão: nsu da NF ou extraída da discriminação."""
    if not nota:
        return None
    nsu = (getattr(nota, 'nsu', None) or '').strip()
    if nsu:
        return nsu
    if getattr(nota, 'discriminacao', None):
        from notasfiscais.utils import extrair_autorizacao
        return extrair_autorizacao(nota.discriminacao)
    return None


def propagar_autorizacao_nota_para_contas_receber(nota, *, apenas_vazias=True):
    """
    Grava autorização (AUT / STONE ID) nas CAR vinculadas à NF.
    Se apenas_vazias, não sobrescreve CAR que já tem autorização.
    Retorna quantidade de CAR atualizadas.
    """
    from .models import ContaAReceber

    if not nota or not getattr(nota, 'pk', None):
        return 0
    auth = _autorizacao_da_nota(nota)
    if not auth:
        return 0
    qs = ContaAReceber.objects.filter(nota_id=nota.pk)
    if apenas_vazias:
        from django.db.models import Q
        qs = qs.filter(Q(autorizacao__isnull=True) | Q(autorizacao=''))
    return qs.update(autorizacao=auth)


def sincronizar_autorizacao_car_da_nota(*, empresa_id=None, dry_run=False):
    """
    Corrige CAR sem autorização quando a NF vinculada tem nsu ou STONEID/AUT na discriminação.
    Também preenche nsu vazio na NF quando só existe na discriminação.
    Retorna dict com contadores.
    """
    from django.db import transaction
    from django.db.models import Q

    from contasareceber.models import ContaAReceber
    from notasfiscais.models import NotaFiscalServico

    stats = {'notas_nsu': 0, 'car': 0, 'sem_auth': 0}

    nf_qs = NotaFiscalServico.objects.exclude(discriminacao='').exclude(discriminacao__isnull=True)
    if empresa_id:
        nf_qs = nf_qs.filter(empresa_id=empresa_id)

    notas_nsu_ids = []
    for nf in nf_qs.iterator():
        auth = _autorizacao_da_nota(nf)
        if auth and not (nf.nsu or '').strip():
            notas_nsu_ids.append((nf.pk, auth))

    car_qs = ContaAReceber.objects.filter(
        nota_id__isnull=False,
    ).filter(Q(autorizacao__isnull=True) | Q(autorizacao='')).select_related('nota')
    if empresa_id:
        car_qs = car_qs.filter(empresa_id=empresa_id)

    car_updates = []
    for car in car_qs.iterator():
        auth = _autorizacao_da_nota(car.nota)
        if not auth:
            stats['sem_auth'] += 1
            continue
        car_updates.append((car.pk, auth))

    if dry_run:
        stats['notas_nsu'] = len(notas_nsu_ids)
        stats['car'] = len(car_updates)
        return stats

    with transaction.atomic():
        for nf_id, auth in notas_nsu_ids:
            NotaFiscalServico.objects.filter(pk=nf_id).update(nsu=auth)
        stats['notas_nsu'] = len(notas_nsu_ids)

        for car_id, auth in car_updates:
            ContaAReceber.objects.filter(pk=car_id).update(autorizacao=auth)
        stats['car'] = len(car_updates)

    return stats
