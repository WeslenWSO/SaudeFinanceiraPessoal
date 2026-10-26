"""Clonar lançamento de faturamento médico (ex.: convênio + particular no mesmo atendimento)."""

from __future__ import annotations

from django.db import transaction

from faturamento_medico.models import FaturamentoMedico, ItemServico

_CAMPOS_FATURAMENTO = (
    'lote',
    'guia',
    'senha',
    'carteirinha',
    'nome',
    'nome_associado',
    'codigo_servico',
    'servico',
    'data_autorizacao',
    'data',
    'porte',
    'qt',
    'valor',
    'local',
    'medico',
    'anestesista',
    'convenio',
    'receber_por',
    'apartamento_enfermaria',
    'urgencia',
    'observacao',
    'cpf',
    'horario',
    'horario_inicio',
    'horario_fim',
    'prioridade',
    'status_agendamento',
    'motivo_cancelamento',
    'medico_solicitante',
    'tecnico',
    'checkin_por',
    'agendado_por',
    'tag',
    'indicacao_clinica',
    'descricao',
    'codigo_relatorio',
    'link_laudo',
    'link_viewer',
    'link_fastshare',
    'laudo_expires_at',
    'agendado_via',
    'percentual_imposto',
    'percentual_comissao',
)

_CAMPOS_ITEM = (
    'codigo_servico',
    'servico',
    'porte',
    'qt',
    'valor',
    'valor_desconto',
    'valor_acrescimo',
    'valor_pago',
    'percentual',
    'modalidade',
    'com_contraste',
    'com_sedacao',
)


@transaction.atomic
def clonar_faturamento(
    origem: FaturamentoMedico,
    *,
    copiar_itens: bool = True,
) -> FaturamentoMedico:
    dados = {campo: getattr(origem, campo) for campo in _CAMPOS_FATURAMENTO}
    prefixo_obs = f'Clonado do lançamento #{origem.pk}.'
    obs = (dados.get('observacao') or '').strip()
    dados['observacao'] = f'{prefixo_obs}\n{obs}'.strip() if obs else prefixo_obs
    dados['lote'] = ''
    dados['medcloud_schedule_id'] = None

    novo = FaturamentoMedico(
        empresa_id=origem.empresa_id,
        status='pendente',
        guia_lancada='',
        numero_guia_lancada='',
        nota_fiscal='',
        codigo_fechamento=None,
        data_fechamento=None,
        marcado_acerto_caixa=False,
        caixa_acerto='',
        valor_imposto=0,
        valor_comissao=0,
        **dados,
    )
    novo.save()

    if copiar_itens:
        for item in origem.itens_servico.all().order_by('data_criacao', 'pk'):
            ItemServico.objects.create(
                faturamento=novo,
                conferido=False,
                status_conferencia='PENDENTE',
                valor_glosa=0,
                data_recorrencia=None,
                **{campo: getattr(item, campo) for campo in _CAMPOS_ITEM},
            )

    novo.atualizar_total()
    return novo
