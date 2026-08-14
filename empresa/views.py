import json
import logging
import re
import sys

import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_GET
from .models import Empresa, UsuarioEmpresa
from .forms import EmpresaForm, EmpresaIntegracaoForm
from .certificado_windows import listar_certificados_windows_por_cnpj
from socio.models import Socio
from fornecedor.models import Fornecedor

logger = logging.getLogger(__name__)


class SociosSaveBlocked(Exception):
    """Sincronização de sócios impedida (ex.: vínculo com rateio)."""


# APIs públicas de CNPJ costumam bloquear requisições sem User-Agent.
_HEADERS_CNPJ_API = {
    "User-Agent": "SaudeFinanceira/1.0 (Django; consulta CNPJ cadastro empresa)",
    "Accept": "application/json",
}


def _limpar_cnpj(cnpj_str):
    """Retorna apenas os dígitos do CNPJ."""
    if not cnpj_str:
        return ""
    return re.sub(r"\D", "", str(cnpj_str).strip())


def _fornecedor_da_empresa_por_cnpj(empresa_id, cnpj_limpo):
    """Fornecedor da empresa (sessão) com o mesmo CNPJ (14 dígitos), ou None."""
    if not empresa_id or len(cnpj_limpo) != 14:
        return None
    qs = Fornecedor.objects.filter(empresa_id=empresa_id).prefetch_related("socios")
    fn = qs.filter(cnpj=cnpj_limpo).first()
    if fn:
        return fn
    for fn in qs:
        if _limpar_cnpj(fn.cnpj) == cnpj_limpo:
            return fn
    return None


# Regex para remover prefixo numérico do tipo (ex: "52-" em "52-Sócio com Capital")
_REMOVER_PREFIXO_TIPO_QSA = re.compile(r"^\d+\s*-\s*", re.IGNORECASE)


def parse_qsa_string(txt):
    """
    Parseia uma string do QSA no formato "NOME COMPLETO - 52-Sócio com Capital".
    Separa pelo primeiro " - ", remove prefixo numérico do tipo, retorna (nome, tipo).
    Se tipo vier vazio, usa fallback "Sócio".
    """
    return _parse_qsa_item(txt)


def _parse_qsa_item(item):
    """
    Converte um item do QSA (string ou dict) em (nome, tipo).
    - String: "NOME COMPLETO - 52-Sócio com Capital" -> (nome, "Sócio com Capital")
    - Dict: mapeia chaves comuns (nome/socio, qualificacao/tipo) para (nome, tipo).
    tipo nunca fica vazio: fallback "Sócio".
    """
    if item is None:
        return ("", "Sócio")
    if isinstance(item, str):
        s = (item or "").strip()
        if not s:
            return ("", "Sócio")
        idx = s.find(" - ")
        if idx < 0:
            return (s, "Sócio")
        nome = s[:idx].strip()
        resto = s[idx + 3 :].strip()  # após " - "
        tipo = _REMOVER_PREFIXO_TIPO_QSA.sub("", resto).strip() or "Sócio"
        return (nome, tipo)
    if isinstance(item, dict):
        nome = (
            (item.get("socio") or item.get("nome") or item.get("nome_socio"))
            or ""
        ).strip()
        tipo = (
            (
                item.get("tipo")
                or item.get("qualificacao")
                or item.get("qualificacao_socio")
            )
            or ""
        ).strip() or "Sócio"
        return (nome, tipo)
    return ("", "Sócio")


def _normalizar_payload_receita(dados):
    """
    Normaliza o dict retornado pela API de CNPJ (ReceitaWS ou similar).
    Garante chaves: razao, nome_fantasia, socios (lista de {socio, tipo}).
    qsa pode vir como lista de strings ("NOME - 52-Tipo") ou de dicts.
    """
    if not dados or not isinstance(dados, dict):
        return {"razao": "", "nome_fantasia": "", "socios": []}
    razao = (
        dados.get("razao")
        or dados.get("razao_social")
        or dados.get("nome")
        or ""
    )
    nome_fantasia = (
        dados.get("nome_fantasia")
        or dados.get("fantasia")
        or ""
    )
    raw_socios = dados.get("qsa") or dados.get("socios") or []
    if not isinstance(raw_socios, list):
        raw_socios = []
    socios = []
    for item in raw_socios:
        nome, tipo = _parse_qsa_item(item)
        socios.append({"socio": nome, "tipo": tipo or "Sócio"})
    return {"razao": razao or "", "nome_fantasia": nome_fantasia or "", "socios": socios}


def _formatar_data_br_api(val):
    """ISO, YYYYMMDD (só dígitos) ou texto já em DD/MM/AAAA → exibição DD/MM/AAAA."""
    if val is None:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        return s
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    if re.match(r"^\d{8}$", s):
        return f"{s[6:8]}/{s[4:6]}/{s[0:4]}"
    return s


def _formatar_telefone_digitos_br(digitos):
    """Formata telefone BR com 10 ou 11 dígitos para exibição."""
    d = re.sub(r"\D", "", str(digitos or ""))
    if len(d) == 11:
        return f"({d[0:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[0:2]}) {d[2:6]}-{d[6:]}"
    return str(digitos or "").strip()


def _telefone_brasilapi(dados):
    """
    Na BrasilAPI, `ddd_telefone_1` às vezes traz o número completo (10/11 dígitos)
    e `telefone_1` vem vazio; em outros casos DDD (2) vem em um campo e o resto no outro.
    """
    linhas = []
    for i in (1, 2):
        raw_ddd = str(dados.get(f"ddd_telefone_{i}") or "").strip()
        raw_tel = str(dados.get(f"telefone_{i}") or "").strip()
        dig_ddd = re.sub(r"\D", "", raw_ddd)
        dig_tel = re.sub(r"\D", "", raw_tel)
        if not dig_ddd and not dig_tel:
            continue
        if dig_tel:
            if len(dig_ddd) <= 2 and dig_ddd:
                linhas.append(_formatar_telefone_digitos_br(dig_ddd + dig_tel))
            elif len(dig_ddd) >= 10:
                linhas.append(_formatar_telefone_digitos_br(dig_ddd))
            else:
                linhas.append(f"({dig_ddd}) {raw_tel}".strip())
        elif dig_ddd:
            if len(dig_ddd) >= 10:
                linhas.append(_formatar_telefone_digitos_br(dig_ddd))
            else:
                linhas.append(raw_ddd)
    if linhas:
        return " / ".join(linhas)
    return str(dados.get("telefone") or "").strip()


def _normalizar_detalhes_cnpj_api(dados):
    """
    Campos extras para o modal (BrasilAPI Minha Receita e ReceitaWS).
    Retorna: atividades, natureza_juridica, porte, data_abertura,
    situacao_cadastral, data_situacao_cadastral, cidade_uf, telefone.
    """
    out = {
        "atividades": [],
        "natureza_juridica": "",
        "porte": "",
        "data_abertura": "",
        "situacao_cadastral": "",
        "data_situacao_cadastral": "",
        "cidade_uf": "",
        "telefone": "",
        "cep": "",
        "logradouro": "",
        "numero": "",
        "complemento": "",
        "bairro": "",
        "email": "",
    }
    if not dados or not isinstance(dados, dict):
        return out

    is_brasilapi = "cnae_fiscal" in dados or (
        "cnaes_secundarios" in dados and isinstance(dados.get("cnaes_secundarios"), list)
    )

    def _set_cidade_uf():
        mun = (dados.get("municipio") or "").strip()
        uf = (dados.get("uf") or "").strip()
        if mun and uf:
            out["cidade_uf"] = f"{mun} - {uf}"
        elif mun:
            out["cidade_uf"] = mun
        elif uf:
            out["cidade_uf"] = uf

    if is_brasilapi:
        cf = dados.get("cnae_fiscal")
        cfd = (dados.get("cnae_fiscal_descricao") or "").strip()
        if cf is not None and str(cf).strip():
            line = f"{cf} - {cfd}" if cfd else str(cf).strip()
            out["atividades"].append(line)
        elif cfd:
            out["atividades"].append(cfd)
        for item in dados.get("cnaes_secundarios") or []:
            if not isinstance(item, dict):
                continue
            cod = item.get("codigo") or item.get("cnae")
            desc = (item.get("descricao") or "").strip()
            if cod is not None and str(cod).strip():
                out["atividades"].append(f"{cod} - {desc}" if desc else str(cod).strip())
            elif desc:
                out["atividades"].append(desc)

        nj = dados.get("natureza_juridica")
        if isinstance(nj, dict):
            out["natureza_juridica"] = (nj.get("descricao") or nj.get("nome") or "").strip()
        else:
            out["natureza_juridica"] = str(nj or "").strip()

        porte_txt = (dados.get("descricao_porte") or "").strip()
        porte_cod = str(dados.get("porte") or "").strip()
        if porte_txt and porte_cod:
            out["porte"] = f"{porte_cod} - {porte_txt}"
        elif porte_txt:
            out["porte"] = porte_txt
        else:
            out["porte"] = porte_cod

        out["data_abertura"] = _formatar_data_br_api(
            dados.get("data_inicio_atividade") or dados.get("data_abertura")
        )
        out["situacao_cadastral"] = str(
            dados.get("descricao_situacao_cadastral")
            or dados.get("situacao_cadastral")
            or ""
        ).strip()
        out["data_situacao_cadastral"] = _formatar_data_br_api(
            dados.get("data_situacao_cadastral") or dados.get("data_situacao_especial")
        )
        _set_cidade_uf()
        out["telefone"] = _telefone_brasilapi(dados)
        out["cep"] = str(dados.get("cep") or "").strip()
        out["logradouro"] = str(dados.get("logradouro") or "").strip()
        out["numero"] = str(dados.get("numero") or "").strip()
        out["complemento"] = str(dados.get("complemento") or "").strip()
        out["bairro"] = str(dados.get("bairro") or "").strip()
        out["email"] = str(dados.get("email") or "").strip()
        return out

    for item in dados.get("atividade_principal") or []:
        if isinstance(item, dict):
            code = (item.get("code") or "").strip()
            text = (item.get("text") or "").strip()
            if code and text:
                out["atividades"].append(f"{code} - {text}")
            elif code or text:
                out["atividades"].append(code or text)
    for item in dados.get("atividades_secundarias") or []:
        if isinstance(item, dict):
            code = (item.get("code") or "").strip()
            text = (item.get("text") or "").strip()
            if code and text:
                out["atividades"].append(f"{code} - {text}")
            elif code or text:
                out["atividades"].append(code or text)

    out["natureza_juridica"] = str(dados.get("natureza_juridica") or "").strip()
    out["porte"] = str(dados.get("porte") or "").strip()
    out["data_abertura"] = _formatar_data_br_api(
        dados.get("abertura") or dados.get("data_inicio_atividade")
    )
    out["situacao_cadastral"] = str(dados.get("situacao") or "").strip()
    out["data_situacao_cadastral"] = _formatar_data_br_api(dados.get("data_situacao"))
    out["telefone"] = str(dados.get("telefone") or "").strip()
    out["cep"] = str(dados.get("cep") or "").strip()
    out["logradouro"] = str(dados.get("logradouro") or "").strip()
    out["numero"] = str(dados.get("numero") or "").strip()
    out["complemento"] = str(dados.get("complemento") or "").strip()
    out["bairro"] = str(dados.get("bairro") or "").strip()
    out["email"] = str(dados.get("email") or "").strip()
    _set_cidade_uf()
    return out


def _detalhes_a_partir_fornecedor(fn):
    """
    Mesmo formato de `detalhes` usado pelo modal do extrato, a partir do cadastro local.
    """
    txt = (fn.atividades_cnae or "").strip()
    atividades = [ln.strip() for ln in txt.splitlines() if ln.strip()] if txt else []
    return {
        "atividades": atividades,
        "natureza_juridica": (fn.natureza_juridica or "").strip(),
        "porte": (fn.porte or "").strip(),
        "data_abertura": _formatar_data_br_api(fn.data_abertura) if fn.data_abertura else "",
        "situacao_cadastral": (fn.situacao_cadastral or "").strip(),
        "data_situacao_cadastral": (
            _formatar_data_br_api(fn.data_situacao_cadastral)
            if fn.data_situacao_cadastral
            else ""
        ),
        "cidade_uf": (fn.cidade_uf or "").strip(),
        "telefone": _formatar_telefone_digitos_br(fn.telefone) if fn.telefone else "",
        "cep": (fn.cep or "").strip(),
        "logradouro": (fn.logradouro or "").strip(),
        "numero": (fn.numero or "").strip(),
        "complemento": (fn.complemento or "").strip(),
        "bairro": (fn.bairro or "").strip(),
        "email": (fn.endereco_eletronico or "").strip(),
    }


def _socios_json_de_fornecedor(fn):
    """Lista no formato esperado pelo modal do extrato."""
    return [
        {"socio": s.nome, "tipo": (s.tipo_qualificacao or "").strip() or "Sócio"}
        for s in fn.socios.all()
    ]


def _consultar_cnpj_receita_externa(cnpj_limpo):
    """
    Consulta CNPJ em API pública quando ainda não existe no cadastro local.
    Ordem: BrasilAPI (estável) → ReceitaWS (fallback; pode bloquear IP de datacenter).
    Retorna dict compatível com _normalizar_payload_receita ou {"erro": "mensagem"}.
    """
    # 1) BrasilAPI — https://brasilapi.com.br/docs#tag/CNPJ
    try:
        url = "https://brasilapi.com.br/api/cnpj/v1/%s" % cnpj_limpo
        r = requests.get(url, headers=_HEADERS_CNPJ_API, timeout=25)
        if r.status_code == 404:
            return {
                "erro": "CNPJ não encontrado na base pública da Receita (inválido ou inexistente).",
            }
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and not data.get("erro"):
            return data
    except requests.exceptions.RequestException as e:
        logger.warning("BrasilAPI indisponível para CNPJ %s: %s", cnpj_limpo, e)
    except ValueError as e:
        logger.warning("BrasilAPI JSON inválido para CNPJ %s: %s", cnpj_limpo, e)

    # 2) ReceitaWS (legado)
    try:
        url = "https://www.receitaws.com.br/v1/cnpj/%s" % cnpj_limpo
        r = requests.get(url, headers=_HEADERS_CNPJ_API, timeout=25)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return {"erro": "Resposta inválida da consulta de CNPJ."}
        if data.get("status") == "ERROR" or data.get("erro"):
            return {
                "erro": (data.get("message") or data.get("erro") or "CNPJ não encontrado."),
            }
        return data
    except requests.exceptions.RequestException as e:
        logger.exception("Falha ao consultar CNPJ %s na ReceitaWS: %s", cnpj_limpo, e)
        return {
            "erro": "Não foi possível consultar o CNPJ agora (rede ou serviço indisponível). Tente de novo em instantes.",
        }
    except ValueError:
        return {"erro": "Resposta inválida da API de CNPJ."}


def _salvar_socios_da_api(empresa, socios_list):
    """
    Sincroniza sócios (app ``socio``) com a lista enviada, sem apagar registros
    ainda referenciados por lançamentos de rateio ou itens de regra de rateio.

    Cada item pode incluir ``id`` (pk do ``Socio``). Itens sem ``id`` são
    casados a registros existentes pelo par (socio, tipo) quando possível
    (ex.: retorno da API de CNPJ sem ids).

    Retorna ``(True, None)`` ou ``(False, mensagem)``.
    """
    from regrarateio.models import LancamentoRateio, RegraRateioItem

    if not socios_list or not isinstance(socios_list, list):
        socios_list = []

    existing = {s.pk: s for s in Socio.objects.filter(empresa=empresa)}

    rows = []
    for item in socios_list:
        if not isinstance(item, dict):
            continue
        nome = (item.get("socio") or item.get("nome") or "").strip()
        tipo = (item.get("tipo") or item.get("qualificacao") or "Sócio").strip() or "Sócio"
        if not nome or not tipo:
            continue
        nome = nome[:50]
        tipo = tipo[:50]
        pk = None
        sid = item.get("id")
        if sid is not None and sid != "":
            try:
                cand = int(sid)
                if cand in existing:
                    pk = cand
            except (TypeError, ValueError):
                pass
        rows.append({"pk": pk, "nome": nome, "tipo": tipo})

    claimed = {r["pk"] for r in rows if r["pk"] is not None}

    for r in rows:
        if r["pk"] is not None:
            continue
        for epk, s in existing.items():
            if epk in claimed:
                continue
            if s.socio.strip() == r["nome"] and (s.tipo or "").strip() == r["tipo"]:
                r["pk"] = epk
                claimed.add(epk)
                break

    new_instances = []
    for r in rows:
        if r["pk"] is not None:
            s = existing[r["pk"]]
            if s.socio != r["nome"] or s.tipo != r["tipo"]:
                s.socio = r["nome"]
                s.tipo = r["tipo"]
                s.save(update_fields=["socio", "tipo"])
        else:
            new_instances.append(Socio(empresa=empresa, socio=r["nome"], tipo=r["tipo"]))

    if new_instances:
        Socio.objects.bulk_create(new_instances)
        for r, inst in zip([x for x in rows if x["pk"] is None], new_instances):
            r["pk"] = inst.pk

    wanted_pks = {r["pk"] for r in rows if r["pk"] is not None}
    to_remove = [epk for epk in existing if epk not in wanted_pks]

    blocked = []
    for epk in to_remove:
        if LancamentoRateio.objects.filter(socio_id=epk).exists():
            blocked.append(existing[epk].socio)
        elif RegraRateioItem.objects.filter(socios_id=epk).exists():
            blocked.append(existing[epk].socio)

    if blocked:
        return (
            False,
            "Não é possível remover sócios vinculados a lançamentos de rateio ou a itens "
            "de regra de rateio: " + ", ".join(blocked),
        )

    if to_remove:
        Socio.objects.filter(pk__in=to_remove).delete()
    return True, None


@login_required
def lista_empresas(request):
    """Lista todas as empresas que o usuário tem acesso"""
    usuario_empresas = UsuarioEmpresa.objects.filter(
        usuario=request.user, 
        ativo=True
    ).select_related('empresa')
    
    # Filtra apenas empresas ativas para seleção
    empresas_ativas = [ue.empresa for ue in usuario_empresas if ue.empresa.status == 'Ativa']

    context = {
        'usuario_empresas': usuario_empresas,
        'empresa_atual': request.session.get('empresa_nome'),
        'object_list': empresas_ativas,
        'todas_empresas': [ue.empresa for ue in usuario_empresas]  # Para mostrar todas incluindo inativas
        
    }
    
    # Se não há empresa selecionada, usa o template de seleção rápida
    if not request.session.get('empresa_id'):
        return render(request, 'empresa/selecao_rapida.html', context)
    
    # Se já há empresa selecionada, usa o template de lista normal
    return render(request, 'empresa/Emp_List.html', context)

@login_required
@require_http_methods(["POST"])
def selecionar_empresa_ajax(request):
    """Seleciona uma empresa via AJAX"""
    empresa_id = request.POST.get('empresa_id')
    
    
    if not empresa_id:
        return JsonResponse({'success': False, 'message': 'ID da empresa não fornecido'})
    
    try:
        usuario_empresa = UsuarioEmpresa.objects.get(
            usuario=request.user,
            empresa_id=empresa_id,
            ativo=True
        )
        
        # Verifica se a empresa está ativa
        if usuario_empresa.empresa.status != 'Ativa':
            return JsonResponse({
                'success': False, 
                'message': 'Não é possível selecionar uma empresa inativa.'
            })
        
        # Salva a empresa selecionada na sessão
        request.session['empresa_id'] = empresa_id
        request.session['empresa_nome'] = usuario_empresa.empresa.razao
        request.session['regime_tributario'] = usuario_empresa.empresa.regime_tributario

        return JsonResponse({
            'success': True,
            'message': f'Empresa {usuario_empresa.empresa.razao} selecionada com sucesso!',
            'redirect_url': reverse('faturamento_medico:ftlistar'),
            'empresa': {
                'id': usuario_empresa.empresa.id,
                'razao': usuario_empresa.empresa.razao,
                'nome_fantasia': usuario_empresa.empresa.nome_fantasia or '',
                'cnpj': usuario_empresa.empresa.cnpj
            }
        })
        
    except UsuarioEmpresa.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'message': 'Empresa não encontrada ou acesso negado.'
        })

@login_required
def selecionar_empresa(request, empresa_id):
    """Seleciona uma empresa para o usuário"""
    
    try:
        usuario_empresa = UsuarioEmpresa.objects.get(
            usuario=request.user,
            empresa_id=empresa_id,
            ativo=True
        )
        
        # Verifica se a empresa está ativa
        if usuario_empresa.empresa.status != 'Ativa':
            messages.error(request, 'Não é possível selecionar uma empresa inativa.')
            return redirect('empresa:lista')
        
        # Salva a empresa selecionada na sessão
        request.session['empresa_id'] = empresa_id
        request.session['empresa_nome'] = usuario_empresa.empresa.razao
        request.session['regime_tributario'] = usuario_empresa.empresa.regime_tributario
        
        
        messages.success(request, f'Empresa {usuario_empresa.empresa.razao} selecionada com sucesso!')
        
        # Sempre vai para o dashboard (início) após escolher a empresa
        return redirect('faturamento_medico:ftlistar')
        
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada ou acesso negado.')
        return redirect('empresa:lista')

@login_required
def trocar_empresa(request):
    """Permite ao usuário trocar de empresa"""
    empresa_atual = request.session.get('empresa_nome', 'Empresa')
    
    # Remove a empresa atual da sessão
    if 'empresa_id' in request.session:
        del request.session['empresa_id']
    if 'empresa_nome' in request.session:
        del request.session['empresa_nome']
    
    messages.info(request, f'Empresa {empresa_atual} removida. Selecione uma nova empresa para continuar.')
    return redirect('empresa:lista')

@login_required
def empresa_atual(request):
    """Retorna informações da empresa atual"""
    empresa_id = request.session.get('empresa_id')
    if empresa_id:
        try:
            empresa = Empresa.objects.get(id=empresa_id)
            return JsonResponse({
                'id': empresa.id,
                'razao': empresa.razao,
                'nome_fantasia': empresa.nome_fantasia or '',
                'cnpj': empresa.cnpj,
                'status': empresa.status
            })
        except Empresa.DoesNotExist:
            return JsonResponse({'error': 'Empresa não encontrada'}, status=404)
    else:
        return JsonResponse({'error': 'Nenhuma empresa selecionada'}, status=400)


@login_required
@require_GET
def buscar_empresa_por_cnpj_ajax(request):
    """
    GET /empresa/api/buscar-cnpj/?cnpj=...

    Ordem (economiza API pública):
    1) Com verificar_fornecedor_local=1: fornecedor já cadastrado na empresa da sessão.
    2) Empresa (cadastro global) com esse CNPJ — retorna sócios; sem API.
    3) Caso contrário: BrasilAPI → ReceitaWS.

    verificar_fornecedor_local=1 é usado pelo extrato; o cadastro de Empresa (tenant) não envia,
    para não confundir com fornecedor.

    pode_cadastrar_fornecedor: True só na resposta vinda da API externa, se houver empresa_id
    na sessão e ainda não existir fornecedor com esse CNPJ para essa empresa.
    """
    cnpj_raw = request.GET.get("cnpj", "").strip()
    cnpj_limpo = _limpar_cnpj(cnpj_raw)
    if len(cnpj_limpo) != 14:
        return JsonResponse(
            {"success": False, "message": "CNPJ inválido. Informe 14 dígitos."},
            status=400,
        )

    empresa_sessao_id = request.session.get("empresa_id")
    verificar_fn = request.GET.get("verificar_fornecedor_local") in (
        "1",
        "true",
        "yes",
        "on",
    )

    if verificar_fn:
        fn = _fornecedor_da_empresa_por_cnpj(empresa_sessao_id, cnpj_limpo)
        if fn:
            det_fn = _detalhes_a_partir_fornecedor(fn)
            tel_exibir = _formatar_telefone_digitos_br(fn.telefone) if fn.telefone else ""
            return JsonResponse(
                {
                    "success": True,
                    "economia_api": True,
                    "message": "Fornecedor já cadastrado para esta empresa.",
                    "empresa": {
                        "cnpj": cnpj_limpo,
                        "razao": fn.razao,
                        "nome_fantasia": (fn.nome_fantasia or "").strip(),
                        "telefone": tel_exibir,
                        "socios": _socios_json_de_fornecedor(fn),
                        "ja_cadastrada": False,
                        "fornecedor_cadastrado": True,
                        "fornecedor_id": fn.id,
                        "detalhes": det_fn,
                        "pode_cadastrar_fornecedor": False,
                    },
                }
            )

    try:
        empresa = Empresa.objects.get(cnpj=cnpj_limpo)
        socios_db = [
            {"id": s.pk, "socio": s.socio, "tipo": (s.tipo or "Sócio")}
            for s in empresa.socio_set.all()
        ]
        return JsonResponse(
            {
                "success": True,
                "economia_api": True,
                "message": "Empresa já cadastrada no sistema (sem consulta à API).",
                "empresa": {
                    "cnpj": empresa.cnpj,
                    "razao": empresa.razao,
                    "nome_fantasia": empresa.nome_fantasia or "",
                    "telefone": (empresa.telefone or "").strip() if empresa.telefone else "",
                    "socios": socios_db,
                    "ja_cadastrada": True,
                    "fornecedor_cadastrado": False,
                    "detalhes": {},
                    "pode_cadastrar_fornecedor": False,
                },
            }
        )
    except Empresa.DoesNotExist:
        pass

    dados_ext = _consultar_cnpj_receita_externa(cnpj_limpo)
    if isinstance(dados_ext, dict) and dados_ext.get("erro"):
        msg = dados_ext["erro"]
        st = 404 if "não encontrado" in msg.lower() or "inválido" in msg.lower() else 502
        return JsonResponse({"success": False, "message": msg}, status=st)

    norm = _normalizar_payload_receita(dados_ext)
    if not (norm.get("razao") or "").strip():
        return JsonResponse(
            {
                "success": False,
                "message": "A consulta não retornou razão social. Verifique o CNPJ.",
            },
            status=422,
        )

    detalhes = _normalizar_detalhes_cnpj_api(dados_ext)

    # Botão "Cadastrar fornecedor" só faz sentido após consulta real à API e se
    # ainda não existir fornecedor para esta empresa + CNPJ (e houver empresa na sessão).
    ja_forn = (
        _fornecedor_da_empresa_por_cnpj(empresa_sessao_id, cnpj_limpo)
        if empresa_sessao_id
        else None
    )
    pode_cadastrar_fornecedor = bool(empresa_sessao_id) and ja_forn is None

    tel_api = (detalhes.get("telefone") or "").strip()

    return JsonResponse(
        {
            "success": True,
            "economia_api": False,
            "message": "Dados obtidos da consulta pública (Receita). Confira antes de salvar.",
            "empresa": {
                "cnpj": cnpj_limpo,
                "razao": norm["razao"],
                "nome_fantasia": norm["nome_fantasia"],
                "telefone": tel_api,
                "socios": norm["socios"],
                "ja_cadastrada": False,
                "fornecedor_cadastrado": False,
                "detalhes": detalhes,
                "pode_cadastrar_fornecedor": pode_cadastrar_fornecedor,
            },
        }
    )


@login_required
def empresa_create(request):
    """Cria uma nova empresa e seus sócios (socios_json no POST)."""
    render_socios_json = None
    if request.method == 'POST':
        form = EmpresaForm(request.POST, request.FILES)
        raw = (request.POST.get("socios_json") or "").strip()
        if form.is_valid():
            socios_list = []
            if raw:
                try:
                    socios_list = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    socios_list = []
            if not isinstance(socios_list, list):
                socios_list = []
            try:
                with transaction.atomic():
                    empresa = form.save()
                    UsuarioEmpresa.objects.create(
                        usuario=request.user,
                        empresa=empresa,
                        ativo=True,
                    )
                    ok, msg = _salvar_socios_da_api(empresa, socios_list)
                    if not ok:
                        raise SociosSaveBlocked(msg)
            except SociosSaveBlocked as e:
                messages.error(request, e.args[0] if e.args else "Não foi possível salvar os sócios.")
                form = EmpresaForm(request.POST, request.FILES)
                render_socios_json = raw or "[]"
            else:
                messages.success(request, 'Empresa criada com sucesso!')
                return redirect('empresa:empresa_sucesso')
        else:
            messages.error(
                request,
                'Não foi possível salvar a empresa. Corrija os campos destacados e tente novamente.',
            )
            render_socios_json = raw or "[]"
    else:
        form = EmpresaForm()
    context = {
        'form': form,
        'descricao': 'Cadastrar Nova Empresa',
        'socios_json_initial': render_socios_json if render_socios_json is not None else '[]',
    }
    return render(request, 'empresa/empresa_form.html', context)

@login_required
def empresa_update(request, pk):
    """Atualiza uma empresa existente e seus sócios (socios_json no POST)."""
    empresa = get_object_or_404(Empresa, pk=pk)
    render_socios_json = None
    if request.method == 'POST':
        form = EmpresaForm(request.POST, request.FILES, instance=empresa)
        raw = (request.POST.get("socios_json") or "").strip()
        if form.is_valid():
            socios_list = []
            if raw:
                try:
                    socios_list = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    socios_list = []
            if not isinstance(socios_list, list):
                socios_list = []
            try:
                with transaction.atomic():
                    empresa = form.save()
                    ok, msg = _salvar_socios_da_api(empresa, socios_list)
                    if not ok:
                        raise SociosSaveBlocked(msg)
            except SociosSaveBlocked as e:
                messages.error(request, e.args[0] if e.args else "Não foi possível salvar os sócios.")
                empresa = get_object_or_404(Empresa, pk=pk)
                form = EmpresaForm(request.POST, request.FILES, instance=empresa)
                render_socios_json = raw or "[]"
            else:
                messages.success(request, 'Empresa atualizada com sucesso!')
                return redirect('empresa:lista')
        else:
            messages.error(
                request,
                'Não foi possível salvar. Corrija os campos destacados e tente novamente.',
            )
            render_socios_json = raw or "[]"
    else:
        form = EmpresaForm(instance=empresa)
    if render_socios_json is not None:
        socios_json_initial = render_socios_json
    else:
        socios_json_initial = json.dumps(
            [
                {"id": s.pk, "socio": s.socio, "tipo": s.tipo or "Sócio"}
                for s in empresa.socio_set.order_by("pk")
            ],
            ensure_ascii=False,
        )
    context = {
        'form': form,
        'descricao': 'Alterar a Empresa',
        'socios_json_initial': socios_json_initial,
    }
    return render(request, 'empresa/empresa_form.html', context)


@login_required
def empresa_integracao(request, pk):
    """NFS-e nacional, cópias XML, portal e Sicoob — fora do cadastro principal."""
    empresa = get_object_or_404(Empresa, pk=pk)
    if request.method == "POST":
        form = EmpresaIntegracaoForm(request.POST, request.FILES, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuração de integração salva.")
            return redirect("empresa:empresa_integracao", pk=pk)
        messages.error(
            request,
            "Não foi possível salvar. Corrija os campos destacados e tente novamente.",
        )
    else:
        form = EmpresaIntegracaoForm(instance=empresa)
    return render(
        request,
        "empresa/empresa_integracao_form.html",
        {
            "form": form,
            "empresa": empresa,
            "descricao": f"Configuração de integração — {empresa.razao}",
        },
    )


@login_required
def empresa_detail(request, pk):
    """Exibe detalhes de uma empresa (dados do cadastro no banco)."""
    empresa = get_object_or_404(Empresa, pk=pk)
    # Dados do banco no formato esperado pelo template (sem chamar API ReceitaWs)
    socios_db = list(empresa.socio_set.all())
    dad = {
        "nome": empresa.razao,
        "cnpj": empresa.cnpj,
        "fantasia": empresa.nome_fantasia or "",
        "qsa": [{"nome": s.socio, "qual": s.tipo or "Sócio"} for s in socios_db],
    }
    sid = request.session.get("empresa_id")
    try:
        eh_sessao = int(sid) == int(empresa.pk) if sid is not None else False
    except (TypeError, ValueError):
        eh_sessao = str(sid) == str(empresa.pk)
    context = {
        "object": empresa,
        "dad": dad,
        "descricao": f"Detalhes da Empresa: {empresa.razao}",
        "eh_empresa_da_sessao": eh_sessao,
    }
    return render(request, "empresa_detail.html", context)


@login_required
@require_GET
def certificados_windows_por_cnpj(request):
    """
    Lista certificados Windows (Personal) cujo Subject contém o CNPJ informado.
    GET ?cnpj= (14 dígitos). Uso: formulário da empresa ao informar CNPJ.
    """
    cnpj_raw = (request.GET.get("cnpj") or "").strip()
    cnpj = _limpar_cnpj(cnpj_raw)
    if len(cnpj) != 14:
        return JsonResponse(
            {"ok": False, "message": "Informe um CNPJ com 14 dígitos."},
            status=400,
        )
    if sys.platform != "win32":
        return JsonResponse(
            {
                "ok": True,
                "cnpj": cnpj,
                "certificados": [],
                "aviso": "Busca de certificado no repositório Windows só está disponível quando o Django roda em Windows.",
            }
        )
    try:
        certs = listar_certificados_windows_por_cnpj(cnpj)
    except Exception as e:
        logger.exception("certificados_windows_por_cnpj")
        return JsonResponse({"ok": False, "message": str(e)}, status=500)
    return JsonResponse({"ok": True, "cnpj": cnpj, "certificados": certs})


def certificados_windows_por_empresa_sessao(request):
    """
    Lista certificados instalados no Windows (repositório Personal) cujo Subject
    contém o CNPJ da empresa **selecionada na sessão** (não exporta chave privada).
    """
    empresa_id = request.session.get("empresa_id")
    if not empresa_id:
        return JsonResponse(
            {"ok": False, "message": "Selecione uma empresa para continuar."},
            status=400,
        )
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    cnpj = _limpar_cnpj(empresa.cnpj)
    if len(cnpj) != 14:
        return JsonResponse(
            {"ok": False, "message": "CNPJ da empresa selecionada inválido (esperado 14 dígitos)."},
            status=400,
        )
    if sys.platform != "win32":
        return JsonResponse(
            {
                "ok": True,
                "cnpj": cnpj,
                "empresa_razao": empresa.razao,
                "certificados": [],
                "aviso": "Esta busca só roda no servidor Windows (certutil + repositório Personal).",
            }
        )
    try:
        certs = listar_certificados_windows_por_cnpj(cnpj)
    except Exception as e:
        logger.exception("certificados_windows_por_empresa_sessao")
        return JsonResponse(
            {"ok": False, "message": f"Erro ao consultar certificados: {e}"},
            status=500,
        )
    return JsonResponse(
        {
            "ok": True,
            "cnpj": cnpj,
            "empresa_razao": empresa.razao,
            "certificados": certs,
        }
    )


@login_required
def empresa_toggle_status(request, pk):
    """Alterna o status de uma empresa entre Ativa e Inativa"""
    empresa = get_object_or_404(Empresa, pk=pk)
    
    # Se a empresa está sendo inativada e é a empresa atual, remove da sessão
    if empresa.status == 'Ativa' and request.session.get('empresa_id') == pk:
        if 'empresa_id' in request.session:
            del request.session['empresa_id']
        if 'empresa_nome' in request.session:
            del request.session['empresa_nome']
        messages.warning(request, f'Empresa {empresa.razao} foi inativada e removida da sessão.')
    else:
        if empresa.status == 'Ativa':
            empresa.status = 'Inativa'
            messages.info(request, f'Empresa {empresa.razao} foi inativada.')
        else:
            empresa.status = 'Ativa'
            messages.info(request, f'Empresa {empresa.razao} foi ativada.')
    
    empresa.save()
    return redirect('empresa:lista')

@login_required
def empresa_sucesso(request):
    """Página de sucesso após criar empresa"""
    return render(request, 'empresa_sucesso.html') 