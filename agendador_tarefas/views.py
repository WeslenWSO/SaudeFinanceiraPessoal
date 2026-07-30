from datetime import date
import calendar as cal_mod
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from empresa.models import Empresa

from .forms import TarefaAgendadaForm
from .models import TarefaAgendada, registrar_passagem_responsavel


def _empresa_sessao(request):
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return None
    return Empresa.objects.filter(pk=empresa_id).first()


def _escopo_tarefas(empresa):
    """Tarefas gerais + da empresa selecionada."""
    filtro = Q(empresa__isnull=True)
    if empresa:
        filtro |= Q(empresa=empresa)
    return filtro


def _usuario_pode_tarefa(tarefa, empresa):
    if tarefa.empresa_id is None:
        return True
    return empresa is not None and tarefa.empresa_id == empresa.id


def _filtros_get(request):
    mes = request.GET.get('mes')
    ano = request.GET.get('ano')
    status = (request.GET.get('status') or '').strip()
    q = (request.GET.get('q') or '').strip()
    vista = (request.GET.get('vista') or 'calendario').strip()
    hoje = date.today()
    try:
        mes = int(mes) if mes else hoje.month
    except (TypeError, ValueError):
        mes = hoje.month
    try:
        ano = int(ano) if ano else hoje.year
    except (TypeError, ValueError):
        ano = hoje.year
    if mes < 1 or mes > 12:
        mes = hoje.month
    if vista not in ('calendario', 'lista'):
        vista = 'calendario'
    return mes, ano, status, q, vista


def _queryset_tarefas(empresa, mes, ano, status, q):
    qs = (
        TarefaAgendada.objects.filter(_escopo_tarefas(empresa))
        .filter(data__month=mes, data__year=ano)
        .select_related('criado_por', 'concluido_por', 'empresa')
        .order_by('data', 'hora_inicio', 'titulo')
    )
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(descricao__icontains=q)
            | Q(responsavel__icontains=q)
        )
    return qs


def _montar_calendario(mes, ano, tarefas):
    semanas = cal_mod.monthcalendar(ano, mes)
    por_dia = defaultdict(list)
    for t in tarefas:
        por_dia[t.data].append(t)

    semanas_ctx = []
    for semana in semanas:
        dias = []
        for dia_num in semana:
            if dia_num == 0:
                dias.append({'numero': 0, 'tarefas': [], 'fora_mes': True})
            else:
                d = date(ano, mes, dia_num)
                dias.append({
                    'numero': dia_num,
                    'data': d,
                    'tarefas': por_dia.get(d, []),
                    'fora_mes': False,
                    'hoje': d == date.today(),
                    'domingo': d.weekday() == 6,
                })
        semanas_ctx.append(dias)

    mes_anterior = mes - 1 if mes > 1 else 12
    ano_anterior = ano if mes > 1 else ano - 1
    mes_proximo = mes + 1 if mes < 12 else 1
    ano_proximo = ano if mes < 12 else ano + 1

    nomes_mes = [
        '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
    ]

    return {
        'semanas': semanas_ctx,
        'mes_nome': nomes_mes[mes],
        'mes_anterior': mes_anterior,
        'ano_anterior': ano_anterior,
        'mes_proximo': mes_proximo,
        'ano_proximo': ano_proximo,
    }


def _contexto_listagem(request, empresa):
    mes, ano, status, q, vista = _filtros_get(request)
    tarefas = _queryset_tarefas(empresa, mes, ano, status, q)
    ctx = {
        'title': 'Agendador de Tarefas',
        'empresa': empresa,
        'tarefas': tarefas,
        'filtros': {'mes': mes, 'ano': ano, 'status': status, 'q': q, 'vista': vista},
        'status_choices': TarefaAgendada.STATUS_CHOICES,
        'calendario': _montar_calendario(mes, ano, tarefas),
    }
    return ctx, vista


@login_required
def tarefa_listar(request):
    empresa = _empresa_sessao(request)
    ctx, vista = _contexto_listagem(request, empresa)
    template = 'agendador_tarefas/lista.html' if vista == 'lista' else 'agendador_tarefas/calendario.html'
    return render(request, template, ctx)


@login_required
def tarefa_criar(request):
    empresa = _empresa_sessao(request)
    hoje = date.today()
    initial = {
        'competencia_mes': hoje.month,
        'competencia_ano': hoje.year,
        'data': hoje,
        'previsao_conclusao': hoje,
        'status': TarefaAgendada.STATUS_PENDENTE,
        'tarefa_geral': not empresa,
    }
    if request.method == 'POST':
        form = TarefaAgendadaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                tarefa = form.save(commit=False)
                if form.cleaned_data.get('tarefa_geral') or not empresa:
                    tarefa.empresa = None
                else:
                    tarefa.empresa = empresa
                tarefa.criado_por = request.user
                if tarefa.status == TarefaAgendada.STATUS_CONCLUIDO and not tarefa.data_conclusao:
                    tarefa.data_conclusao = timezone.localdate()
                    tarefa.concluido_por = request.user
                tarefa.save()
                registrar_passagem_responsavel(
                    tarefa, '', tarefa.responsavel, request.user,
                    observacao=form.cleaned_data.get('observacao_passagem') or 'Atribuição inicial',
                )
            messages.success(request, f'Tarefa "{tarefa.titulo}" criada.')
            return redirect('agendador_tarefas:listar')
    else:
        form = TarefaAgendadaForm(initial=initial)

    return render(request, 'agendador_tarefas/form.html', {
        'title': 'Nova tarefa',
        'form': form,
        'empresa': empresa,
    })


@login_required
def tarefa_editar(request, pk):
    empresa = _empresa_sessao(request)
    tarefa = get_object_or_404(
        TarefaAgendada.objects.prefetch_related('logs_responsavel__alterado_por'),
        pk=pk,
    )
    if not _usuario_pode_tarefa(tarefa, empresa):
        messages.error(request, 'Tarefa não disponível.')
        return redirect('agendador_tarefas:listar')

    if request.method == 'POST':
        form = TarefaAgendadaForm(request.POST, instance=tarefa)
        if form.is_valid():
            responsavel_anterior = tarefa.responsavel
            with transaction.atomic():
                obj = form.save(commit=False)
                if form.cleaned_data.get('tarefa_geral'):
                    obj.empresa = None
                elif empresa and not tarefa.is_geral:
                    obj.empresa = empresa
                if obj.status == TarefaAgendada.STATUS_CONCLUIDO:
                    if not obj.data_conclusao:
                        obj.data_conclusao = timezone.localdate()
                    if not obj.concluido_por_id:
                        obj.concluido_por = request.user
                elif obj.status != TarefaAgendada.STATUS_CONCLUIDO:
                    obj.concluido_por = None
                    obj.data_conclusao = None
                obj.save()
                registrar_passagem_responsavel(
                    obj, responsavel_anterior, obj.responsavel, request.user,
                    observacao=form.cleaned_data.get('observacao_passagem') or '',
                )
            messages.success(request, f'Tarefa "{obj.titulo}" atualizada.')
            return redirect(
                f"{reverse('agendador_tarefas:listar')}"
                f"?mes={obj.data.month}&ano={obj.data.year}"
            )
        messages.error(request, 'Não foi possível salvar. Verifique os campos destacados.')
    else:
        form = TarefaAgendadaForm(instance=tarefa, initial={'tarefa_geral': tarefa.is_geral})

    return render(request, 'agendador_tarefas/form.html', {
        'title': f'Editar — {tarefa.titulo}',
        'form': form,
        'empresa': empresa,
        'tarefa': tarefa,
        'logs_responsavel': tarefa.logs_responsavel.all(),
    })


@login_required
@require_POST
def tarefa_excluir(request, pk):
    empresa = _empresa_sessao(request)
    tarefa = get_object_or_404(TarefaAgendada, pk=pk)
    if not _usuario_pode_tarefa(tarefa, empresa):
        messages.error(request, 'Tarefa não disponível.')
        return redirect('agendador_tarefas:listar')
    titulo = tarefa.titulo
    tarefa.delete()
    messages.success(request, f'Tarefa "{titulo}" excluída.')
    return redirect('agendador_tarefas:listar')


@login_required
@require_POST
def tarefa_alterar_status(request, pk):
    empresa = _empresa_sessao(request)
    tarefa = get_object_or_404(TarefaAgendada, pk=pk)
    if not _usuario_pode_tarefa(tarefa, empresa):
        messages.error(request, 'Tarefa não disponível.')
        return redirect('agendador_tarefas:listar')
    novo = (request.POST.get('status') or '').strip()
    validos = {c[0] for c in TarefaAgendada.STATUS_CHOICES}
    if novo not in validos:
        messages.error(request, 'Status inválido.')
        return redirect('agendador_tarefas:listar')

    tarefa.status = novo
    if novo == TarefaAgendada.STATUS_CONCLUIDO:
        tarefa.data_conclusao = timezone.localdate()
        tarefa.concluido_por = request.user
    else:
        tarefa.data_conclusao = None
        tarefa.concluido_por = None
    tarefa.save(update_fields=['status', 'data_conclusao', 'concluido_por', 'atualizado_em'])
    messages.success(request, f'Status de "{tarefa.titulo}" atualizado.')
    return redirect('agendador_tarefas:listar')
