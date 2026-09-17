"""Importação e envio fiscal de serviços Conta Azul."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError
from django.utils import timezone

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.models import ServicoContaAzul

_CHAVES_CCLASSTRIB = (
    'codigo_classificacao_tributaria',
    'c_class_trib',
    'cClassTrib',
    'classificacao_tributaria',
    'codigo_cclasstrib',
)
_CHAVES_NBS = (
    'codigo_nbs',
    'c_nbs',
    'cNBS',
    'nbs',
    'codigo_c_nbs',
)
_CHAVES_INDICADOR = (
    'indicador_operacao',
    'codigo_indicador_operacao',
    'indicador_da_operacao',
    'c_ind_op',
    'cIndOp',
    'ind_op',
    'indop',
)
_CHAVES_NATUREZA = (
    'natureza_operacao',
    'natureza_operacional',
    'natureza_da_operacao',
)
_CHAVES_SERVICO_MUNICIPAL = (
    'codigo_servico_municipal',
    'codigo_municipio_servico',
    'codigo_servico',
)
_CHAVES_ALIQUOTA_IBS = (
    'aliquota_ibs_estadual',
    'aliquota_ibs',
    'ibs_aliquota',
    'aliquotaIbs',
)
_CHAVES_ALIQUOTA_IBS_MUN = (
    'aliquota_ibs_municipal',
    'ibs_municipal_aliquota',
)
_CHAVES_ALIQUOTA_CBS = (
    'aliquota_cbs',
    'cbs_aliquota',
    'aliquotaCbs',
)
_BLOCOS_ANINHADOS = (
    'dados_fiscais',
    'reforma_tributaria',
    'ibscbs',
    'ibs_cbs',
    'classificacao_tributaria',
    'fiscal',
)

# Chaves usadas no PATCH (primeira com valor no GET tem precedência na inspeção)
PATCH_CCLASSTRIB = 'codigo_classificacao_tributaria'
PATCH_NBS = 'codigo_nbs'
PATCH_INDICADOR = 'codigo_indicador_operacao'
PATCH_NATUREZA = 'natureza_operacao'


def _valor_texto(val: Any) -> str:
    if val is None:
        return ''
    if isinstance(val, dict):
        for chave in ('codigo', 'id', 'valor', 'code'):
            interno = val.get(chave)
            if interno not in (None, ''):
                return str(interno).strip()
        return ''
    return str(val).strip()


def _primeira_chave(item: dict, chaves: tuple[str, ...]) -> str:
    if not isinstance(item, dict):
        return ''
    for chave in chaves:
        if chave in item and item[chave] not in (None, ''):
            return _valor_texto(item[chave])
    for bloco in _BLOCOS_ANINHADOS:
        nested = item.get(bloco)
        if isinstance(nested, dict):
            valor = _primeira_chave(nested, chaves)
            if valor:
                return valor
    return ''


def _primeira_decimal(item: dict, chaves: tuple[str, ...]) -> Decimal | None:
    if not isinstance(item, dict):
        return None
    for chave in chaves:
        if chave not in item or item[chave] in (None, ''):
            continue
        try:
            return Decimal(str(item[chave]))
        except (InvalidOperation, ValueError, TypeError):
            continue
    for bloco in _BLOCOS_ANINHADOS:
        nested = item.get(bloco)
        if isinstance(nested, dict):
            valor = _primeira_decimal(nested, chaves)
            if valor is not None:
                return valor
    return None


def _natureza_de_item(item: dict) -> str:
    natureza = _primeira_chave(item, _CHAVES_NATUREZA)
    bloco = item.get('natureza_operacional')
    if not natureza and isinstance(bloco, dict):
        natureza = _valor_texto(bloco.get('descricao') or bloco.get('nome') or bloco.get('label'))
    # API costuma devolver só UUID em natureza_operacional — não gravar como texto legível.
    if natureza and len(natureza) >= 32 and '-' in natureza:
        return ''
    return natureza


def extrair_fiscal_de_resposta(item: dict) -> dict:
    """Extrai campos fiscais da reforma tributária de um JSON de serviço Conta Azul."""
    item = item or {}
    natureza = _natureza_de_item(item)
    return {
        'natureza_operacao': natureza,
        'codigo_servico_municipal': _primeira_chave(item, _CHAVES_SERVICO_MUNICIPAL),
        'c_class_trib': _primeira_chave(item, _CHAVES_CCLASSTRIB),
        'codigo_nbs': _primeira_chave(item, _CHAVES_NBS),
        'indicador_operacao': _primeira_chave(item, _CHAVES_INDICADOR),
        'aliquota_ibs': _primeira_decimal(item, _CHAVES_ALIQUOTA_IBS),
        'aliquota_ibs_municipal': _primeira_decimal(item, _CHAVES_ALIQUOTA_IBS_MUN),
        'aliquota_cbs': _primeira_decimal(item, _CHAVES_ALIQUOTA_CBS),
    }


def chaves_fiscais_presentes(item: dict) -> dict[str, str]:
    """Mapeia qual chave da API contém cada campo fiscal (para inspeção)."""
    item = item or {}
    resultado: dict[str, str] = {}

    def _buscar(chaves: tuple[str, ...], prefixo: str = '') -> str:
        for chave in chaves:
            caminho = f'{prefixo}{chave}' if prefixo else chave
            alvo = item
            if prefixo:
                partes = prefixo.rstrip('.').split('.')
                for parte in partes:
                    if isinstance(alvo, dict):
                        alvo = alvo.get(parte)
                    else:
                        alvo = None
                        break
            if isinstance(alvo, dict) and chave in alvo and alvo[chave] not in (None, ''):
                return caminho
        for bloco in _BLOCOS_ANINHADOS:
            nested = item.get(bloco)
            if isinstance(nested, dict):
                interno = _buscar(chaves, f'{bloco}.')
                if interno:
                    return interno
        return ''

    resultado['natureza_operacao'] = _buscar(_CHAVES_NATUREZA)
    resultado['codigo_servico_municipal'] = _buscar(_CHAVES_SERVICO_MUNICIPAL)
    resultado['c_class_trib'] = _buscar(_CHAVES_CCLASSTRIB)
    resultado['codigo_nbs'] = _buscar(_CHAVES_NBS)
    resultado['indicador_operacao'] = _buscar(_CHAVES_INDICADOR)
    resultado['aliquota_ibs'] = _buscar(_CHAVES_ALIQUOTA_IBS)
    resultado['aliquota_ibs_municipal'] = _buscar(_CHAVES_ALIQUOTA_IBS_MUN)
    resultado['aliquota_cbs'] = _buscar(_CHAVES_ALIQUOTA_CBS)
    return resultado


def montar_payload_fiscal(servico: ServicoContaAzul) -> dict:
    """Monta PATCH parcial com campos fiscais editáveis (sem alíquotas IBS/CBS)."""
    payload: dict[str, str] = {}
    if servico.natureza_operacao:
        payload[PATCH_NATUREZA] = servico.natureza_operacao.strip()
    if servico.codigo_servico_municipal:
        payload['codigo_municipio_servico'] = servico.codigo_servico_municipal.strip()
    if servico.c_class_trib:
        payload[PATCH_CCLASSTRIB] = servico.c_class_trib.strip()
    if servico.codigo_nbs:
        payload[PATCH_NBS] = servico.codigo_nbs.strip()
    if servico.indicador_operacao:
        payload[PATCH_INDICADOR] = servico.indicador_operacao.strip()
    return payload


def _status_de_item(item: dict) -> str:
    status = str(item.get('status') or ServicoContaAzul.STATUS_ATIVO).upper()
    if status in (ServicoContaAzul.STATUS_ATIVO, ServicoContaAzul.STATUS_INATIVO):
        return status
    return ServicoContaAzul.STATUS_ATIVO


def _preco_de_item(item: dict) -> Decimal | None:
    for chave in ('preco', 'valor', 'preco_venda'):
        if chave not in item or item[chave] in (None, ''):
            continue
        try:
            return Decimal(str(item[chave]))
        except (InvalidOperation, ValueError, TypeError):
            continue
    return None


def aplicar_item_api_ao_servico(
    servico: ServicoContaAzul,
    item: dict,
    *,
    preservar_fiscal_pendente: bool = True,
) -> None:
    fiscal = extrair_fiscal_de_resposta(item)
    servico.codigo = str(item.get('codigo') or servico.codigo or '')[:50]
    servico.descricao = str(item.get('descricao') or servico.descricao or '')[:300]
    servico.status = _status_de_item(item)
    preco = _preco_de_item(item)
    if preco is not None:
        servico.preco = preco
    servico.codigo_cnae = str(item.get('codigo_cnae') or servico.codigo_cnae or '')[:20]
    servico.lei_116 = str(item.get('lei_116') or servico.lei_116 or '')[:20]

    mun = fiscal['codigo_servico_municipal'][:20]
    if mun:
        servico.codigo_servico_municipal = mun

    if not (preservar_fiscal_pendente and servico.fiscal_pendente_envio):
        # API v1 costuma não devolver IBS/CBS — não sobrescrever com vazio.
        if fiscal['natureza_operacao']:
            servico.natureza_operacao = fiscal['natureza_operacao'][:80]
        if fiscal['c_class_trib']:
            servico.c_class_trib = fiscal['c_class_trib'][:20]
        if fiscal['codigo_nbs']:
            servico.codigo_nbs = fiscal['codigo_nbs'][:30]
        if fiscal['indicador_operacao']:
            servico.indicador_operacao = fiscal['indicador_operacao'][:20]

    if fiscal['aliquota_ibs'] is not None:
        servico.aliquota_ibs = fiscal['aliquota_ibs']
    if fiscal['aliquota_ibs_municipal'] is not None:
        servico.aliquota_ibs_municipal = fiscal['aliquota_ibs_municipal']
    if fiscal['aliquota_cbs'] is not None:
        servico.aliquota_cbs = fiscal['aliquota_cbs']


def importar_servicos(
    empresa,
    client: ContaAzulClient,
    *,
    dry_run: bool = False,
) -> dict:
    stats = {'criados': 0, 'atualizados': 0, 'erros': 0}
    try:
        itens = client.buscar_servicos()
    except ContaAzulAPIError as exc:
        return {**stats, 'erro': str(exc)}

    agora = timezone.now()
    for item in itens:
        ca_id = str(item.get('id') or item.get('uuid') or '').strip()
        if not ca_id:
            stats['erros'] += 1
            continue
        if dry_run:
            stats['criados'] += 1
            continue
        try:
            detalhe = item
            if ca_id:
                try:
                    detalhe_api = client.buscar_servico_por_id(ca_id)
                    if detalhe_api:
                        detalhe = detalhe_api
                except ContaAzulAPIError:
                    detalhe = item
            obj = ServicoContaAzul.objects.filter(empresa=empresa, conta_azul_id=ca_id).first()
            criado = obj is None
            if criado:
                obj = ServicoContaAzul(empresa=empresa, conta_azul_id=ca_id, importado_em=agora)
            aplicar_item_api_ao_servico(obj, detalhe)
            if criado:
                obj.importado_em = agora
            obj.save()
            if criado:
                stats['criados'] += 1
            else:
                stats['atualizados'] += 1
        except IntegrityError:
            stats['erros'] += 1
    return stats


def enviar_fiscal_servico(
    empresa,
    client: ContaAzulClient,
    servico: ServicoContaAzul,
) -> dict:
    if servico.empresa_id != empresa.pk:
        raise ContaAzulAPIError('Serviço não pertence à empresa informada.')
    ca_id = (servico.conta_azul_id or '').strip()
    if not ca_id:
        raise ContaAzulAPIError('Serviço sem ID Conta Azul.')

    payload = montar_payload_fiscal(servico)
    if not payload:
        raise ContaAzulAPIError('Informe ao menos cClassTrib, NBS ou Indicador da operação.')

    fiscal_local = {
        'natureza_operacao': servico.natureza_operacao,
        'codigo_servico_municipal': servico.codigo_servico_municipal,
        'c_class_trib': servico.c_class_trib,
        'codigo_nbs': servico.codigo_nbs,
        'indicador_operacao': servico.indicador_operacao,
    }

    client.atualizar_servico(ca_id, payload)
    detalhe = client.buscar_servico_por_id(ca_id)
    if detalhe:
        aplicar_item_api_ao_servico(servico, detalhe, preservar_fiscal_pendente=True)

    for campo, valor in fiscal_local.items():
        if valor and not (getattr(servico, campo) or '').strip():
            setattr(servico, campo, valor)

    if not fiscal_gravado_na_resposta_api(detalhe):
        servico.fiscal_pendente_envio = True
        servico.save()
        raise ContaAzulAPIError(
            'O Conta Azul respondeu à requisição, mas não gravou cClassTrib/NBS/Indicador. '
            'A API v1 ainda não persiste esses campos de Reforma Tributária — '
            'preencha manualmente no cadastro do serviço no Conta Azul Pro.'
        )

    agora = timezone.now()
    servico.fiscal_pendente_envio = False
    servico.enviado_em = agora
    servico.save()
    return {'ok': True, 'payload': payload}


def enviar_servicos_pendentes(empresa, client: ContaAzulClient) -> dict:
    stats = {'enviados': 0, 'erros': 0, 'detalhes': []}
    pendentes = ServicoContaAzul.objects.filter(
        empresa=empresa,
        fiscal_pendente_envio=True,
    ).exclude(conta_azul_id='')
    for servico in pendentes:
        try:
            enviar_fiscal_servico(empresa, client, servico)
            stats['enviados'] += 1
        except ContaAzulAPIError as exc:
            stats['erros'] += 1
            stats['detalhes'].append(f'{servico.codigo or servico.pk}: {exc}')
    return stats


CAMPOS_FISCAIS_REPLICAR = (
    'natureza_operacao',
    'codigo_servico_municipal',
    'c_class_trib',
    'codigo_nbs',
    'indicador_operacao',
)


def servico_tem_dados_fiscais(servico: ServicoContaAzul) -> bool:
    return bool(
        (servico.c_class_trib or '').strip()
        or (servico.codigo_nbs or '').strip()
        or (servico.indicador_operacao or '').strip()
    )


def fiscal_gravado_na_resposta_api(item: dict) -> bool:
    fiscal = extrair_fiscal_de_resposta(item or {})
    return bool(
        (fiscal.get('c_class_trib') or '').strip()
        or (fiscal.get('codigo_nbs') or '').strip()
        or (fiscal.get('indicador_operacao') or '').strip()
    )


def replicar_fiscal_servicos(
    empresa,
    origem: ServicoContaAzul,
    destino_pks: list[int],
) -> dict:
    if origem.empresa_id != empresa.pk:
        raise ContaAzulAPIError('Serviço origem não pertence à empresa.')
    if not servico_tem_dados_fiscais(origem):
        raise ContaAzulAPIError(
            'O serviço origem não possui cClassTrib, NBS ou Indicador para replicar.'
        )

    destino_pks = [pk for pk in destino_pks if pk != origem.pk]
    stats = {'replicados': 0, 'ignorados': 0}
    if not destino_pks:
        return stats

    valores = {campo: getattr(origem, campo) for campo in CAMPOS_FISCAIS_REPLICAR}
    destinos = ServicoContaAzul.objects.filter(empresa=empresa, pk__in=destino_pks)
    for destino in destinos:
        for campo, valor in valores.items():
            setattr(destino, campo, valor)
        destino.fiscal_pendente_envio = True
        destino.save(update_fields=[*CAMPOS_FISCAIS_REPLICAR, 'fiscal_pendente_envio'])
        stats['replicados'] += 1
    stats['ignorados'] = len(destino_pks) - stats['replicados']
    return stats


def enviar_servicos_selecionados(
    empresa,
    client: ContaAzulClient,
    servico_pks: list[int],
) -> dict:
    stats = {'enviados': 0, 'erros': 0, 'detalhes': []}
    if not servico_pks:
        return stats
    servicos = (
        ServicoContaAzul.objects.filter(empresa=empresa, pk__in=servico_pks)
        .exclude(conta_azul_id='')
        .order_by('codigo', 'descricao')
    )
    for servico in servicos:
        try:
            enviar_fiscal_servico(empresa, client, servico)
            stats['enviados'] += 1
        except ContaAzulAPIError as exc:
            stats['erros'] += 1
            stats['detalhes'].append(f'{servico.codigo or servico.pk}: {exc}')
    return stats
