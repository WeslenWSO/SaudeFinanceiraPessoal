"""Sincroniza cobrança (forma de pagamento) e autorização da NFSe para o CAR."""
from __future__ import annotations

from cobranca.models import Cobranca
from notasfiscais.utils import (
    detectar_forma_pagamento_e_vincular,
    extrair_autorizacao,
    _encontra_cobranca_flexivel,
)


def sincronizar_forma_e_autorizacao_nota(nota) -> dict:
    """
    Lê a discriminação da NF (mesmas regras da importação / NFSe em lote),
    atualiza forma_pagamento e nsu na nota e replica nas contas a receber vinculadas.
    """
    from contasareceber.socio_sync import (
        propagar_autorizacao_nota_para_contas_receber,
        propagar_forma_pagamento_nota_para_contas_receber,
    )

    out = {
        'nota_id': getattr(nota, 'pk', None),
        'numero_nota': getattr(nota, 'numero_nota', ''),
        'forma': None,
        'autorizacao': None,
        'mudou_nf': False,
        'motivo': '',
    }
    disc = (getattr(nota, 'discriminacao', None) or '').strip()
    if not disc:
        out['motivo'] = 'sem_discriminacao'
        return out

    campos_update: list[str] = []
    todas_cob = list(Cobranca.objects.all())

    cob, motivo_fp, _ = detectar_forma_pagamento_e_vincular(
        disc,
        todas_cob,
        valor_total_nfse=getattr(nota, 'valor_bruto', None),
        valor_liquido_nfse=getattr(nota, 'valor_liquido', None),
    )
    if not cob:
        from notasfiscais.discriminacao_nfse import discriminacao_valor_coerente

        valor_ref = nota.valor_liquido if nota.valor_liquido is not None else nota.valor_bruto
        if discriminacao_valor_coerente(disc, valor_ref):
            payment_method = nota.extract_payment_method_from_description()
            if payment_method:
                try:
                    cob = Cobranca.objects.get(descricao=payment_method)
                except Cobranca.DoesNotExist:
                    cob = _encontra_cobranca_flexivel(payment_method, todas_cob)

    if cob and nota.forma_pagamento_id != cob.pk:
        nota.forma_pagamento = cob
        campos_update.append('forma_pagamento')
        out['forma'] = cob.descricao
    elif cob:
        out['forma'] = cob.descricao

    auth = (getattr(nota, 'nsu', None) or '').strip() or (extrair_autorizacao(disc) or '').strip()
    if auth and (nota.nsu or '').strip() != auth:
        nota.nsu = auth
        campos_update.append('nsu')
    if auth:
        out['autorizacao'] = auth

    if campos_update:
        nota.save(update_fields=campos_update)
        out['mudou_nf'] = True
    elif cob or auth:
        out['motivo'] = motivo_fp or 'ja_preenchido'

    out['car_forma'] = propagar_forma_pagamento_nota_para_contas_receber(nota)
    out['car_aut'] = propagar_autorizacao_nota_para_contas_receber(nota, apenas_vazias=False)

    if not out['forma'] and not out['autorizacao']:
        out['motivo'] = out['motivo'] or motivo_fp or 'nada_encontrado'

    return out


def sincronizar_forma_e_autorizacao_notas_das_contas(conta_ids, *, empresa_id: int) -> dict:
    """Processa cada NF distinta vinculada às contas selecionadas."""
    from contasareceber.models import ContaAReceber

    contas = (
        ContaAReceber.objects.filter(pk__in=conta_ids, empresa_id=empresa_id)
        .exclude(nota_id__isnull=True)
        .select_related('nota')
    )
    notas_vistas: set[int] = set()
    stats = {
        'notas_processadas': 0,
        'notas_atualizadas': 0,
        'car_forma': 0,
        'car_aut': 0,
        'sem_nota': 0,
        'sem_discriminacao': 0,
        'sem_dados': 0,
    }

    selecionadas = len(conta_ids)
    com_nota = contas.count()
    stats['sem_nota'] = max(0, selecionadas - com_nota)

    for conta in contas:
        nf = conta.nota
        if not nf or nf.pk in notas_vistas:
            continue
        notas_vistas.add(nf.pk)
        stats['notas_processadas'] += 1
        res = sincronizar_forma_e_autorizacao_nota(nf)
        if res.get('mudou_nf'):
            stats['notas_atualizadas'] += 1
        if res.get('motivo') == 'sem_discriminacao':
            stats['sem_discriminacao'] += 1
        if not res.get('forma') and not res.get('autorizacao'):
            stats['sem_dados'] += 1
        stats['car_forma'] += int(res.get('car_forma') or 0)
        stats['car_aut'] += int(res.get('car_aut') or 0)

    return stats
