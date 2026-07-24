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
