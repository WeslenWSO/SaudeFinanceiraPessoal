"""Catálogo de opções do menu e helpers de permissão por usuário."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import User
from django.urls import reverse

from .auth_user import auth_user_de_usuario as lookup_auth_user
from .auth_user import usuario_login_canonico
from .models import PermissaoMenuUsuario


@dataclass
class MenuItemDef:
    codigo: str
    rotulo: str
    icon: str
    secao: str | None = None
    url_name: str | None = None
    url_externa: str | None = None
    url_hash: str | None = None


@dataclass
class MenuSecaoDef:
    codigo: str
    rotulo: str
    icon: str
    dropdown_id: str
    trigger_id: str


SECOES_MENU: tuple[MenuSecaoDef, ...] = (
    MenuSecaoDef('cadastro', 'Cadastro', 'fa-folder-open', 'dropdown-cadastro', 'trigger-cadastro'),
    MenuSecaoDef('faturamento', 'Faturamento', 'fa-file-medical', 'dropdown-faturamento', 'trigger-faturamento'),
    MenuSecaoDef('fiscal', 'Fiscal', 'fa-file-invoice', 'dropdown-fiscal', 'trigger-fiscal'),
    MenuSecaoDef('financeiro', 'Financeiro', 'fa-wallet', 'dropdown-financeiro', 'trigger-financeiro'),
    MenuSecaoDef('relatorios', 'Relatórios', 'fa-chart-bar', 'dropdown-relatorios', 'trigger-relatorios'),
    MenuSecaoDef('tarefas', 'Tarefas', 'fa-tasks', 'dropdown-tarefas', 'trigger-tarefas'),
    MenuSecaoDef('links_uteis', 'Links úteis', 'fa-link', 'dropdown-links-uteis', 'trigger-links-uteis'),
)

ITENS_MENU: tuple[MenuItemDef, ...] = (
    MenuItemDef('dashboard', 'Dashboard', 'fa-cloud', url_name='dashboard:index'),
    MenuItemDef('dashboard_academia', 'Dashboard de Academia', 'fa-dumbbell', url_name='indicadores:dashboard_academia'),
    MenuItemDef('dashboard_por_tipo', 'Dashboard — R/D/I/L', 'fa-chart-pie', 'relatorios', url_name='dashboard:por_tipo'),
    MenuItemDef('empresa', 'Empresa', 'fa-building', 'cadastro', url_name='empresa:lista'),
    MenuItemDef('fornecedor', 'Fornecedor', 'fa-truck', 'cadastro', url_name='fornecedor:fornList'),
    MenuItemDef('cliente', 'Cliente', 'fa-user-tie', 'cadastro', url_name='cliente:clieList'),
    MenuItemDef('cobranca', 'Cobrança', 'fa-credit-card', 'cadastro', url_name='cobranca:cobList'),
    MenuItemDef('categoria', 'Categoria', 'fa-tags', 'cadastro', url_name='categoria:catList'),
    MenuItemDef('socio', 'Sócios', 'fa-users', 'cadastro', url_name='socio:socList'),
    MenuItemDef('regraimposto', 'Regras do Imposto', 'fa-percent', 'cadastro', url_name='regraimposto:ListaRegra'),
    MenuItemDef('regrarateio', 'Regra do Rateio', 'fa-share-nodes', 'cadastro', url_name='regrarateio:regraList'),
    MenuItemDef('usuario', 'Usuário', 'fa-user-cog', 'cadastro', url_name='usuario:usuarioList'),
    MenuItemDef('backup_banco', 'Backup do banco', 'fa-database', 'cadastro', url_name='accounts:backup_banco'),
    MenuItemDef('faturamento_medico', 'Faturamento Médico', 'fa-file-medical', 'faturamento', url_name='faturamento_medico:ftlistar'),
    MenuItemDef('agendador_tarefas', 'Agendador de Tarefas', 'fa-calendar-check', 'tarefas', url_name='agendador_tarefas:listar'),
    MenuItemDef('indicadores', 'Indicadores', 'fa-bullseye', 'cadastro', url_name='indicadores:listar'),
    MenuItemDef('lancamento_vendas_dia', 'Lançamento diário academia', 'fa-calendar-day', 'cadastro', url_name='indicadores:lancamento_vendas_listar'),
    MenuItemDef('atendentes_academia', 'Atendentes academia', 'fa-user-friends', 'cadastro', url_name='indicadores:atendente_listar'),
    MenuItemDef('convenios', 'Convênios', 'fa-hand-holding-medical', 'cadastro', url_name='servicos_medicos:convenio_list'),
    MenuItemDef('cabecalhos', 'Cabeçalhos', 'fa-heading', 'cadastro', url_name='servicos_medicos:cabecalho_list'),
    MenuItemDef('servicos_medicos', 'Serviços Médicos', 'fa-stethoscope', 'cadastro', url_name='servicos_medicos:servicos_list'),
    MenuItemDef('tabela_precos', 'Tabela de Preços', 'fa-table-list', 'cadastro', url_name='servicos_medicos:tabela_list'),
    MenuItemDef('nf_prestado', 'Notas Fiscais Prestado', 'fa-file-invoice-dollar', 'fiscal', url_name='notasfiscais:list'),
    MenuItemDef('dashboard_nfse', 'Dashboard NFSe', 'fa-chart-pie', 'fiscal', url_name='notasfiscais:dashboard'),
    MenuItemDef('apuracao_nfse', 'Apuração NFSe', 'fa-calculator', 'fiscal', url_name='notasfiscais:apuracao_impostos'),
    MenuItemDef('apuracao_simples', 'Apuração Simples', 'fa-scale-balanced', 'fiscal', url_name='notasfiscais:apuracao_simples'),
    MenuItemDef('import_xml', 'Importar XML', 'fa-file-import', 'fiscal', url_name='notasfiscais:import'),
    MenuItemDef('import_cancelamentos', 'Importar cancelamentos (Eventos)', 'fa-ban', 'fiscal', url_name='notasfiscais:import_evento_cancelamento'),
    MenuItemDef('portal_nacional', 'Portal Nacional (SEFIN / DPS)', 'fa-cloud-download-alt', 'fiscal', url_name='notasfiscais:portal_nacional_import'),
    MenuItemDef('portal_extensao', 'Portal (extensão)', 'fa-puzzle-piece', 'fiscal', url_name='notasfiscais:portal_extensao_import'),
    MenuItemDef('nf_entrada', 'NF Comércio e Tomador', 'fa-file-lines', 'fiscal', url_name='notafiscalentrada:listar'),
    MenuItemDef('contas_bancarias', 'Contas Bancárias', 'fa-university', 'financeiro', url_name='extrato:conta_bancaria_list'),
    MenuItemDef('contas_pagar', 'Contas a Pagar', 'fa-money-check-alt', 'financeiro', url_name='contasapagar:listaAPagar'),
    MenuItemDef('categorizar_pagos', 'Categorizar pagos', 'fa-tags', 'financeiro', url_name='contasapagar:categorizar_baixados'),
    MenuItemDef('contas_receber', 'Contas a Receber', 'fa-hand-holding-usd', 'financeiro', url_name='contasareceber:crlistar'),
    MenuItemDef('categorizar_recebidos', 'Categorizar recebidos', 'fa-tags', 'financeiro', url_name='contasareceber:categorizar_baixados'),
    MenuItemDef('extrato_import', 'Extrato Bancário (Importar)', 'fa-file-upload', 'financeiro', url_name='extrato:upload_ofx'),
    MenuItemDef('lancamentos', 'Lançamentos Importados', 'fa-list-ul', 'financeiro', url_name='extrato:lancamento_list'),
    MenuItemDef('movimentos', 'Movimentos / Conciliação', 'fa-exchange-alt', 'financeiro', url_name='extrato:extrato_movimento_list'),
    MenuItemDef('recebiveis_maquininha', 'Recebíveis Maquininha', 'fa-terminal', 'financeiro', url_name='relatoriorecebiveis:relReclist'),
    MenuItemDef('cartoes', 'Cartões de Crédito', 'fa-id-card', 'financeiro', url_name='opcartao:cartao_listar'),
    MenuItemDef('faturas_cartao', 'Faturas de cartão de Crédito', 'fa-credit-card', 'financeiro', url_name='opcartao:fatura_listar'),
    MenuItemDef('emprestimos', 'Empréstimos', 'fa-file-invoice-dollar', 'relatorios', url_name='emprestimos:listar'),
    MenuItemDef('fluxo_caixa', 'Fluxo de Caixa', 'fa-stream', 'relatorios', url_name='fluxo_de_caixa:fluxo_caixa_mensal'),
    MenuItemDef('planejamento', 'Planejamento orçamentário', 'fa-chart-pie', 'relatorios', url_name='planejamento_orcamentario:dashboard'),
    MenuItemDef('relatorio_mensal', 'Relatório mensal (12 meses)', 'fa-calendar-alt', 'relatorios', url_name='dashboard:relatorio_mensal'),
    MenuItemDef('resumo_fechamento', 'Resumo fechamento', 'fa-file-signature', 'relatorios', url_name='dashboard:resumo_fechamento'),
    MenuItemDef('lancamentos_rateio', 'Lançamentos de rateio', 'fa-table-list', 'relatorios', url_name='regrarateio:lancamentoRateioList'),
    MenuItemDef('cr_relatorio', 'Contas a Receber/Recebido', 'fa-receipt', 'relatorios', url_name='contasareceber:crlistar'),
    MenuItemDef('cp_relatorio', 'Contas a Pagar/Pagas', 'fa-file-invoice', 'relatorios', url_hash='#'),
    MenuItemDef('por_categoria', 'Por Categoria', 'fa-tag', 'relatorios', url_hash='#'),
    MenuItemDef('por_socio', 'Por Sócio', 'fa-user-friends', 'relatorios', url_hash='#'),
    MenuItemDef('medcloud_ris', 'Medcloud RIS', 'fa-calendar-check', 'links_uteis', url_externa='https://ris.medcloud.co/calendar'),
    MenuItemDef('conta_azul_erp', 'Conta Azul (sistema)', 'fa-external-link-alt', 'links_uteis', url_externa='https://app.contaazul.com/'),
    MenuItemDef('cielo', 'Cielo', 'fa-credit-card', 'links_uteis', url_externa='https://minhaconta2.cielo.com.br/site/login'),
    MenuItemDef('stone', 'Stone', 'fa-gem', 'links_uteis', url_externa='https://conta.stone.com.br/login'),
)

CODIGOS_MENU = frozenset(item.codigo for item in ITENS_MENU)
MARCADOR_MENU_CONFIGURADO = '__configurado__'
SECOES_POR_CODIGO = {secao.codigo: secao for secao in SECOES_MENU}
ITENS_POR_CODIGO = {item.codigo: item for item in ITENS_MENU}


def auth_user_de_usuario(usuario) -> User | None:
    return lookup_auth_user(usuario)


def permissoes_menu_do_usuario(user: User | None) -> set[str]:
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(CODIGOS_MENU)
    from django.db.utils import OperationalError, ProgrammingError

    user = usuario_login_canonico(user)
    if not user:
        return set()

    marcador = MARCADOR_MENU_CONFIGURADO
    try:
        qs = PermissaoMenuUsuario.objects.filter(usuario=user).exclude(codigo=marcador)
        if PermissaoMenuUsuario.objects.filter(usuario=user, codigo=marcador).exists():
            return set(qs.values_list('codigo', flat=True))
        if qs.exists():
            return set(qs.values_list('codigo', flat=True))
        return set()
    except (ProgrammingError, OperationalError):
        return set(CODIGOS_MENU)


def usuario_pode_menu(user: User | None, codigo: str) -> bool:
    return codigo in permissoes_menu_do_usuario(user)


def _resolver_url(item: MenuItemDef) -> str:
    if item.url_externa:
        return item.url_externa
    if item.url_hash:
        return item.url_hash
    if item.url_name:
        try:
            return reverse(item.url_name)
        except Exception:
            return '#'
    return '#'


def _item_para_template(item: MenuItemDef) -> dict[str, Any]:
    href = _resolver_url(item)
    return {
        'codigo': item.codigo,
        'rotulo': item.rotulo,
        'icon': item.icon,
        'href': href,
        'externo': bool(item.url_externa),
    }


def montar_menu_nav(user: User | None) -> dict[str, Any]:
    permitidos = permissoes_menu_do_usuario(user)
    links: list[dict[str, Any]] = []
    dropdowns: list[dict[str, Any]] = []

    for item in ITENS_MENU:
        if item.codigo == 'backup_banco' and not (user and user.is_superuser):
            continue
        if item.secao is None and item.codigo in permitidos:
            links.append(_item_para_template(item))

    for secao in SECOES_MENU:
        filhos = [
            _item_para_template(item)
            for item in ITENS_MENU
            if item.secao == secao.codigo
            and item.codigo in permitidos
            and not (item.codigo == 'backup_banco' and not (user and user.is_superuser))
        ]
        if filhos:
            dropdowns.append({
                'codigo': secao.codigo,
                'rotulo': secao.rotulo,
                'icon': secao.icon,
                'dropdown_id': secao.dropdown_id,
                'trigger_id': secao.trigger_id,
                'itens': filhos,
            })

    return {'links': links, 'dropdowns': dropdowns}


def opcoes_permissao_por_secao() -> list[dict[str, Any]]:
    """Agrupa itens para checkboxes no cadastro de usuário."""
    secoes: list[dict[str, Any]] = []
    for secao in SECOES_MENU:
        itens = [
            {'codigo': item.codigo, 'rotulo': item.rotulo}
            for item in ITENS_MENU
            if item.secao == secao.codigo
        ]
        if itens:
            secoes.append({'codigo': secao.codigo, 'rotulo': secao.rotulo, 'itens': itens})
    topo = [
        {'codigo': item.codigo, 'rotulo': item.rotulo}
        for item in ITENS_MENU
        if item.secao is None
    ]
    if topo:
        secoes.insert(0, {'codigo': '_topo', 'rotulo': 'Principal', 'itens': topo})
    return secoes
