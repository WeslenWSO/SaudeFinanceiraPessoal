"""Formas de pagamento na grade de acerto de caixa (manual + rateio)."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from cobranca.models import Cobranca

_EPS = Decimal('0.05')


def _dec(raw) -> Decimal | None:
    if raw is None or raw == '':
        return None
    try:
        return Decimal(str(raw).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def _rotulo_cobranca(cob: Cobranca) -> str:
    return (cob.descricao or '').strip().replace('_', ' ')


def pagamentos_manuais_faturamento(faturamento) -> list[dict[str, Any]]:
    raw = getattr(faturamento, 'pagamentos_acerto_json', None)
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = item.get('cobranca_id')
        val = _dec(item.get('valor'))
        if cid is None or val is None or val <= 0:
            continue
        try:
            cob = Cobranca.objects.get(pk=int(cid))
        except (Cobranca.DoesNotExist, TypeError, ValueError):
            continue
        out.append({
            'cobranca_id': cob.pk,
            'rotulo': _rotulo_cobranca(cob),
            'valor': val,
            'valor_fmt': _fmt_moeda(val),
        })
    return out


def pagamentos_da_nota(nota: dict | None, valor_ref: Decimal | None) -> list[dict[str, Any]]:
    if not nota:
        return []
    detalhes = nota.get('pagamentos_detalhados') or []
    if len(detalhes) >= 2:
        out = []
        for p in detalhes:
            val = _dec(p.get('valor'))
            if val is None or val <= 0:
                continue
            out.append({
                'cobranca_id': None,
                'rotulo': (p.get('rotulo') or 'Outros').strip(),
                'valor': val,
                'valor_fmt': p.get('valor_fmt') or _fmt_moeda(val),
            })
        return out
    forma = (nota.get('forma_pagamento_exibicao') or nota.get('forma_pagamento') or '').strip()
    if not forma or forma == '-':
        return []
    val = valor_ref
    if val is None:
        val = _dec(nota.get('valor_liquido')) or _dec(nota.get('valor_bruto'))
    if val is None or val <= 0:
        return []
    return [{
        'cobranca_id': None,
        'rotulo': forma,
        'valor': val,
        'valor_fmt': _fmt_moeda(val),
    }]


def aplicar_pagamentos_acerto_ao_vincular_nota(faturamento, nota) -> list[dict[str, Any]]:
    """
    Preenche pagamentos_acerto_json a partir da discriminação da NF (regra de forma de pagamento).
    Se a discriminação estiver incoerente com o valor, usa só forma já cadastrada na nota.
    """
    from notasfiscais.discriminacao_nfse import discriminacao_valor_coerente
    from notasfiscais.utils import (
        _encontra_cobranca_flexivel,
        detectar_forma_pagamento_e_vincular,
        extrair_forma_pagamento,
    )

    valor_ref = _dec(nota.valor_liquido) or _dec(nota.valor_bruto)
    if valor_ref is None or valor_ref <= 0:
        faturamento.pagamentos_acerto_json = []
        faturamento.save(update_fields=['pagamentos_acerto_json'])
        return []

    cobrancas = list(Cobranca.objects.all())
    pagamentos_json: list[dict] = []
    disc = (nota.discriminacao or '').strip()
    atualizar_nota = False
    update_nf_fields: list[str] = []

    if disc and discriminacao_valor_coerente(disc, valor_ref):
        cob, motivo, segmentos = detectar_forma_pagamento_e_vincular(
            disc,
            cobrancas,
            valor_total_nfse=_dec(nota.valor_bruto),
            valor_liquido_nfse=_dec(nota.valor_liquido),
        )
        if motivo == 'multi_segmentar' and segmentos:
            for seg in segmentos:
                val = seg[0]
                cob_seg = seg[1]
                pagamentos_json.append({'cobranca_id': cob_seg.pk, 'valor': str(val)})
        elif cob is not None and motivo == 'vinculado':
            pagamentos_json.append({'cobranca_id': cob.pk, 'valor': str(valor_ref)})
            if not nota.forma_pagamento_id:
                nota.forma_pagamento = cob
                atualizar_nota = True
                update_nf_fields.append('forma_pagamento')
        else:
            from faturamento_medico.services.vincular_nota_solicitante import pagamentos_detalhados_nota

            for rotulo, val in pagamentos_detalhados_nota(nota):
                forma_txt = extrair_forma_pagamento(disc) or rotulo
                cob_match = _encontra_cobranca_flexivel(forma_txt, cobrancas)
                if not cob_match:
                    cob_match = _encontra_cobranca_flexivel((rotulo or '').upper(), cobrancas)
                if cob_match:
                    pagamentos_json.append({'cobranca_id': cob_match.pk, 'valor': str(val)})
            if not pagamentos_json:
                forma_txt = extrair_forma_pagamento(disc)
                if forma_txt:
                    cob_match = _encontra_cobranca_flexivel(forma_txt, cobrancas)
                    if cob_match:
                        pagamentos_json.append({'cobranca_id': cob_match.pk, 'valor': str(valor_ref)})
                        if not nota.forma_pagamento_id:
                            nota.forma_pagamento = cob_match
                            atualizar_nota = True
                            update_nf_fields.append('forma_pagamento')

    if not pagamentos_json and nota.forma_pagamento_id:
        pagamentos_json.append({'cobranca_id': nota.forma_pagamento_id, 'valor': str(valor_ref)})

    faturamento.pagamentos_acerto_json = pagamentos_json
    faturamento.save(update_fields=['pagamentos_acerto_json'])
    if atualizar_nota and update_nf_fields:
        nota.save(update_fields=update_nf_fields)

    return pagamentos_manuais_faturamento(faturamento)


def pagamentos_efetivos_faturamento(faturamento, nota: dict | None) -> list[dict[str, Any]]:
    manual = pagamentos_manuais_faturamento(faturamento)
    if manual:
        return manual
    valor_ref = None
    if nota:
        valor_ref = _dec(nota.get('valor_liquido')) or _dec(nota.get('valor_bruto'))
    return pagamentos_da_nota(nota, valor_ref)


def texto_forma_pgto(pagamentos: list[dict[str, Any]]) -> str:
    if not pagamentos:
        return '-'
    partes = []
    for p in pagamentos:
        rot = (p.get('rotulo') or '').strip()
        val = p.get('valor_fmt') or _fmt_moeda(p.get('valor'))
        if rot:
            partes.append(f'{rot} R$ {val}')
        else:
            partes.append(f'R$ {val}')
    return ' + '.join(partes)


def _agrupar_rotulo_resumo(forma: str) -> str:
    f = (forma or '').strip().upper()
    if not f or f == '-':
        return 'Sem NF / forma não informada'
    if 'DINHEIRO' in f:
        return 'Dinheiro'
    if 'PIX' in f:
        return 'PIX'
    if 'DEBIT' in f or 'DÉBITO' in f or 'DEBITO' in f:
        return 'Cartão de débito'
    if 'CRED' in f or 'CRÉDITO' in f or 'CREDITO' in f:
        return 'Cartão de crédito'
    return (forma or '').strip() or 'Outros'


def pagamentos_para_resumo(pagamentos: list[dict[str, Any]]) -> list[tuple[str, Decimal]]:
    out: list[tuple[str, Decimal]] = []
    for p in pagamentos:
        rotulo = (p.get('rotulo') or 'Outros').strip()
        val = p.get('valor')
        if val is None:
            continue
        chave = _agrupar_rotulo_resumo(rotulo)
        out.append((chave, Decimal(str(val))))
    return out


def serializar_pagamentos_json(pagamentos: list[dict[str, Any]]) -> str:
    return json.dumps([
        {'cobranca_id': p.get('cobranca_id'), 'valor': str(p.get('valor'))}
        for p in pagamentos
        if p.get('cobranca_id') is not None
    ])


def validar_e_normalizar_pagamentos(
    linhas: list[dict],
    *,
    valor_esperado: Decimal | None,
) -> tuple[list[dict] | None, str | None]:
    if not linhas:
        return [], None
    normalizado: list[dict] = []
    total = Decimal('0')
    for row in linhas:
        cid = row.get('cobranca_id')
        val = _dec(row.get('valor'))
        if cid is None or val is None or val <= 0:
            return None, 'Informe forma de pagamento e valor em cada linha.'
        try:
            cob = Cobranca.objects.get(pk=int(cid))
        except (Cobranca.DoesNotExist, TypeError, ValueError):
            return None, 'Forma de pagamento inválida.'
        normalizado.append({'cobranca_id': cob.pk, 'valor': val})
        total += val
    if valor_esperado is not None and valor_esperado > 0:
        if abs(total - valor_esperado) > _EPS:
            return None, (
                f'A soma (R$ {_fmt_moeda(total)}) deve bater com o valor da NF '
                f'(R$ {_fmt_moeda(valor_esperado)}).'
            )
    return normalizado, None


def _fmt_moeda(val) -> str:
    d = _dec(val) or Decimal('0')
    s = f'{d:.2f}'.replace('.', ',')
    intp, _, dec = s.partition(',')
    intp = intp[::-1]
    chunks = [intp[i:i + 3] for i in range(0, len(intp), 3)]
    return f"{'.'.join(chunks)[::-1]},{dec}"
