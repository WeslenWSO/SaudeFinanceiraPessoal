"""Sincroniza cobrança (forma de pagamento) e autorização da NFSe para o CAR."""
from __future__ import annotations

import re

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


def _digitos_nf(valor: str) -> str:
    d = re.sub(r'\D', '', (valor or '').strip())
    if not d:
        return ''
    return d.lstrip('0') or '0'


def _variantes_numero_nf(numero: str) -> list[str]:
    """Chaves equivalentes entre doc do CAR e número da NF (zeros à esquerda, só dígitos)."""
    bruto = (numero or '').strip()
    if not bruto:
        return []
    out: list[str] = [bruto]
    dig = _digitos_nf(bruto)
    if dig and dig not in out:
        out.append(dig)
    if dig and dig.isdigit():
        for largo in (4, 5, 6, 7, 8, 9, 10):
            pad = dig.zfill(largo)
            if pad not in out:
                out.append(pad)
    return out


def _nf_por_numero_empresa(empresa_id: int, numero: str):
    from notasfiscais.models import NotaFiscalServico

    qs = NotaFiscalServico.objects.filter(
        empresa_id=empresa_id,
        data_cancelamento__isnull=True,
    )
    for chave in _variantes_numero_nf(numero):
        nf = qs.filter(numero_nota=chave).order_by('-pk').first()
        if nf:
            return nf
    dig = _digitos_nf(numero)
    if not dig:
        return None
    for cand in qs.only('pk', 'numero_nota').order_by('-pk')[:800]:
        if _digitos_nf(cand.numero_nota or '') == dig:
            return cand
    return None


def tentar_vincular_nota_conta_por_documento(conta, *, empresa_id: int) -> bool:
    """Liga o título à NFSe quando doc = número da nota (muito comum em títulos pagos)."""
    from contasareceber.models import ContaAReceber

    if not isinstance(conta, ContaAReceber):
        return False
    if conta.nota_id:
        return True
    doc = (conta.doc or '').strip()
    if not doc:
        return False
    nf = _nf_por_numero_empresa(empresa_id, doc)
    if not nf:
        return False
    conta.nota_id = nf.pk
    conta.save(update_fields=['nota_id'])
    return True


def vincular_contas_receber_a_nota_por_doc(nota) -> int:
    """
    Títulos vindos da Conta Azul costumam ter doc = nº da NFS-e, sem FK nota_id.
    Após importar/salvar a NF, liga esses CAR e replica cobrança/AUT.
    """
    from contasareceber.models import ContaAReceber
    from contasareceber.socio_sync import (
        propagar_autorizacao_nota_para_contas_receber,
        propagar_forma_pagamento_nota_para_contas_receber,
    )

    if not nota or not getattr(nota, 'pk', None) or not getattr(nota, 'empresa_id', None):
        return 0
    numero = (getattr(nota, 'numero_nota', None) or '').strip()
    if not numero:
        return 0
    chaves = set(_variantes_numero_nf(numero))
    dig_nf = _digitos_nf(numero)
    qs = ContaAReceber.objects.filter(
        empresa_id=nota.empresa_id,
        nota_id__isnull=True,
    )
    pks: list[int] = []
    for car in qs.filter(doc__in=chaves).only('pk'):
        pks.append(car.pk)
    if dig_nf:
        for car in qs.exclude(pk__in=pks).only('pk', 'doc'):
            if _digitos_nf(car.doc or '') == dig_nf:
                pks.append(car.pk)
    if not pks:
        return 0
    ContaAReceber.objects.filter(pk__in=pks).update(nota_id=nota.pk)
    propagar_forma_pagamento_nota_para_contas_receber(nota)
    propagar_autorizacao_nota_para_contas_receber(nota, apenas_vazias=False)
    return len(pks)


def sincronizar_forma_e_autorizacao_notas_das_contas(conta_ids, *, empresa_id: int) -> dict:
    """Processa cada NF distinta vinculada às contas selecionadas."""
    from contasareceber.models import ContaAReceber

    contas = list(
        ContaAReceber.objects.filter(pk__in=conta_ids, empresa_id=empresa_id).select_related('nota')
    )
    vinculadas_doc = 0
    for conta in contas:
        if not conta.nota_id and tentar_vincular_nota_conta_por_documento(
            conta, empresa_id=empresa_id
        ):
            vinculadas_doc += 1
            conta.refresh_from_db(fields=['nota_id'])
            if conta.nota_id:
                try:
                    conta.nota.refresh_from_db()
                except Exception:
                    pass

    notas_vistas: set[int] = set()
    stats = {
        'notas_processadas': 0,
        'notas_atualizadas': 0,
        'car_forma': 0,
        'car_aut': 0,
        'sem_nota': 0,
        'sem_discriminacao': 0,
        'sem_dados': 0,
        'vinculadas_por_doc': vinculadas_doc,
    }

    selecionadas = len(conta_ids)
    com_nota = sum(1 for c in contas if c.nota_id)
    stats['sem_nota'] = max(0, selecionadas - com_nota)

    for conta in contas:
        if not conta.nota_id:
            continue
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
