import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.shortcuts import redirect
from django.views import View
from django.views.generic.list import ListView
from django.views.generic.edit import UpdateView, CreateView
from django.contrib import messages
from django.db.models import Q
from .models import Convenio, ServicosMedicos, TabelaPreco, Cabecalho
from .forms import ConvenioForm, ReplicarTabelaPrecoForm, ServicosMedicosForm, TabelaPrecoForm
from .permissoes import usuario_pode_editar_tabela_preco_grid
from .replicar_tabela_preco import replicar_tabela_preco
from .tabela_preco_grid import ErroGridTabelaPreco, atualizar_linha_grid
from empresa.models import Empresa

# Convenio Views
class ConvenioList(ListView):
    model = Convenio
    paginate_by = 10
    template_name = "servicos_medicos/convenio_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Convênios'
        context["now"] = timezone.now()
        return context

class ConvenioCreate(CreateView):
    model = Convenio
    form_class = ConvenioForm
    template_name = "servicos_medicos/convenio_form.html"
    success_url = reverse_lazy('servicos_medicos:convenio_list')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Convênio'
        context["titulo"] = 'Convênio'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        messages.success(self.request, "Convênio criado com sucesso.")
        return super().form_valid(form)

class ConvenioUpdate(UpdateView):
    model = Convenio
    form_class = ConvenioForm
    template_name = "servicos_medicos/convenio_form.html"
    success_url = reverse_lazy('servicos_medicos:convenio_list')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "Convênio atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Convênio'
        context["titulo"] = 'Convênio'
        return context

# ServicosMedicos Views
class ServicosMedicosList(ListView):
    model = ServicosMedicos
    paginate_by = 10
    template_name = "servicos_medicos/servicos_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        search_query = self.request.GET.get('q', '')
        if search_query:
            qs = qs.filter(
                Q(codigo__icontains=search_query) |
                Q(servicos__icontains=search_query)
            )
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Serviços Médicos'
        context["now"] = timezone.now()
        return context

class ServicosMedicosCreate(CreateView):
    model = ServicosMedicos
    form_class = ServicosMedicosForm
    template_name = "servicos_medicos/servicos_form.html"
    success_url = reverse_lazy('servicos_medicos:servicos_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Serviço Médico'
        context["titulo"] = 'Serviço Médico'
        return context

    def form_valid(self, form):
        messages.success(self.request, "Serviço Médico criado com sucesso.")
        return super().form_valid(form)

class ServicosMedicosUpdate(UpdateView):
    model = ServicosMedicos
    form_class = ServicosMedicosForm
    template_name = "servicos_medicos/servicos_form.html"
    success_url = reverse_lazy('servicos_medicos:servicos_list')

    def form_valid(self, form):
        messages.success(self.request, "Serviço Médico atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Serviço Médico'
        context["titulo"] = 'Serviço Médico'
        return context

# TabelaPreco Views
class TabelaPrecoList(ListView):
    model = TabelaPreco
    paginate_by = 25
    template_name = "servicos_medicos/tabela_list.html"
    PAGINATE_OPTIONS = (10, 25, 50, 100, 200)

    def get_paginate_by(self, queryset):
        raw = self.request.GET.get('per_page') or self.request.GET.get('paginate_by')
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self.paginate_by
        if value in self.PAGINATE_OPTIONS:
            return value
        return self.paginate_by

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        emp_int = None
        if empresa_id is not None:
            try:
                emp_int = int(empresa_id)
            except (TypeError, ValueError):
                emp_int = None

        cabecalho_id = self.request.GET.get('cabecalho_id')
        cid = None
        if cabecalho_id:
            try:
                cid = int(cabecalho_id)
            except (TypeError, ValueError):
                cid = None

        if cid is not None:
            qs = qs.filter(cabecalho_id=cid)
            if emp_int is not None:
                qs_emp = qs.filter(empresa_id=emp_int)
                if qs_emp.exists():
                    qs = qs_emp
        elif emp_int is not None:
            qs = qs.filter(empresa_id=emp_int)
        search_query = (self.request.GET.get('q') or '').strip()
        if search_query:
            q_upper = search_query.upper()
            if q_upper == "RM":
                qs = qs.filter(
                    Q(codigo_servico__servicos__istartswith="RM-")
                    | Q(codigo_servico__servicos__istartswith="RM ")
                    | Q(codigo_servico__codigo__startswith="411")
                    | Q(codigo_servico__codigo__startswith="RM-")
                )
            else:
                qs = qs.filter(
                    Q(codigo_servico__codigo__icontains=search_query)
                    | Q(codigo_servico__servicos__icontains=search_query)
                )
        qs = qs.select_related('empresa', 'convenio', 'cabecalho', 'codigo_servico').order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Tabela de Preços'
        context["now"] = timezone.now()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            context["cabecalhos"] = Cabecalho.objects.filter(empresa_id=empresa_id)
        else:
            context["cabecalhos"] = Cabecalho.objects.none()
        context["cabecalho_selecionado"] = self.request.GET.get('cabecalho_id', '')
        context["search_query"] = (self.request.GET.get('q') or '').strip()
        context["per_page"] = str(self.get_paginate_by(self.object_list))
        context["paginate_options"] = self.PAGINATE_OPTIONS
        context["grid_editavel"] = usuario_pode_editar_tabela_preco_grid(self.request.user)
        return context


@method_decorator(login_required, name="dispatch")
class TabelaPrecoGridAtualizarView(View):
    def post(self, request):
        if not usuario_pode_editar_tabela_preco_grid(request.user):
            return JsonResponse({"ok": False, "erro": "Sem permissão para editar a grid."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "erro": "JSON inválido."}, status=400)

        try:
            tabela_id = int(payload.get("id"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "erro": "Id da linha inválido."}, status=400)

        empresa_id = request.session.get("empresa_id")
        if empresa_id is not None:
            try:
                empresa_id = int(empresa_id)
            except (TypeError, ValueError):
                empresa_id = None

        campos = {}
        if "servicos" in payload:
            campos["servicos"] = payload.get("servicos")
        if "preco_apartamento" in payload:
            campos["preco_apartamento"] = payload.get("preco_apartamento")
        if "preco_enfermaria" in payload:
            campos["preco_enfermaria"] = payload.get("preco_enfermaria")
        if not campos:
            return JsonResponse({"ok": False, "erro": "Nenhum campo para atualizar."}, status=400)

        try:
            dados = atualizar_linha_grid(
                tabela_preco_id=tabela_id,
                empresa_id=empresa_id,
                **campos,
            )
        except ErroGridTabelaPreco as exc:
            return JsonResponse({"ok": False, "erro": str(exc)}, status=400)

        return JsonResponse({"ok": True, "dados": dados})


class TabelaPrecoCreate(CreateView):
    model = TabelaPreco
    form_class = TabelaPrecoForm
    template_name = "servicos_medicos/tabela_form.html"
    success_url = reverse_lazy('servicos_medicos:tabela_list')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Tabela de Preço'
        context["titulo"] = 'Tabela de Preço'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        messages.success(self.request, "Tabela de Preço criada com sucesso.")
        return super().form_valid(form)

class TabelaPrecoUpdate(UpdateView):
    model = TabelaPreco
    form_class = TabelaPrecoForm
    template_name = "servicos_medicos/tabela_form.html"
    success_url = reverse_lazy('servicos_medicos:tabela_list')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "Tabela de Preço atualizada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Tabela de Preço'
        context["titulo"] = 'Tabela de Preço'
        return context

# Cabecalho Views
class CabecalhoList(ListView):
    model = Cabecalho
    paginate_by = 10
    template_name = "servicos_medicos/cabecalho_list.html"

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-id")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Lista de Cabeçalhos'
        context["now"] = timezone.now()
        return context

class CabecalhoCreate(CreateView):
    model = Cabecalho
    fields = ['empresa', 'convenio', 'nome_tabela']
    template_name = "servicos_medicos/cabecalho_form.html"
    success_url = reverse_lazy('servicos_medicos:cabecalho_list')

    def get_initial(self):
        initial = super().get_initial()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            initial['empresa'] = empresa_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Adicionar Cabeçalho'
        context["titulo"] = 'Cabeçalho'
        return context

    def form_valid(self, form):
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            form.instance.empresa_id = empresa_id
        messages.success(self.request, "Cabeçalho criado com sucesso.")
        return super().form_valid(form)

class CabecalhoUpdate(UpdateView):
    model = Cabecalho
    fields = ['empresa', 'convenio', 'nome_tabela']
    template_name = "servicos_medicos/cabecalho_form.html"
    success_url = reverse_lazy('servicos_medicos:cabecalho_list')

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.session.get('empresa_id')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def form_valid(self, form):
        messages.success(self.request, "Cabeçalho atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["descricao"] = 'Alterar Cabeçalho'
        context["titulo"] = 'Cabeçalho'
        return context


class ReplicarTabelaPrecoView(View):
    template_name = "servicos_medicos/replicar_tabela_preco.html"

    _GET_ID_PARAMS = (
        ("origem", "cabecalho_origem"),
        ("destino", "cabecalho_destino"),
        ("origem_id", "cabecalho_origem"),
        ("destino_id", "cabecalho_destino"),
    )

    def _empresa_id(self, request):
        raw = request.session.get("empresa_id")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _cabecalho_por_id(self, empresa_id: int, raw_id) -> Cabecalho | None:
        """Mesma regra do CLI: busca por pk; valida empresa só se estiver preenchida."""
        if raw_id is None:
            return None
        text = str(raw_id).strip()
        if not text.isdigit():
            return None
        cab = Cabecalho.objects.filter(pk=int(text)).select_related("convenio").first()
        if not cab:
            return None
        if cab.empresa_id is not None and int(cab.empresa_id) != int(empresa_id):
            return None
        return cab

    def _resolver_cabecalhos_post(self, request, empresa_id: int, form):
        """Resolve cabeçalhos pelos ids inteiros (7 → 6), como no manage.py."""
        atualizar = request.POST.get("atualizar_existentes") in ("on", "true", "1")
        origem_id = destino_id = None
        if form.is_valid():
            origem_id = form.cleaned_data.get("cabecalho_origem")
            destino_id = form.cleaned_data.get("cabecalho_destino")
            atualizar = form.cleaned_data.get("atualizar_existentes", atualizar)
        if origem_id is None:
            raw = request.POST.get("cabecalho_origem")
            origem_id = int(raw) if raw and str(raw).strip().isdigit() else None
        if destino_id is None:
            raw = request.POST.get("cabecalho_destino")
            destino_id = int(raw) if raw and str(raw).strip().isdigit() else None
        origem = self._cabecalho_por_id(empresa_id, origem_id)
        destino = self._cabecalho_por_id(empresa_id, destino_id)
        if origem and destino:
            return origem, destino, atualizar, None
        return None, None, atualizar, form.errors

    def get(self, request):
        empresa_id = self._empresa_id(request)
        if not empresa_id:
            messages.error(request, "Selecione a empresa (Medicinarte) antes de replicar.")
            return redirect("empresa:lista")
        initial = {}
        for param, field in self._GET_ID_PARAMS:
            raw = request.GET.get(param)
            if raw and str(raw).strip().isdigit():
                initial[field] = int(str(raw).strip())
        form = ReplicarTabelaPrecoForm(empresa_id=empresa_id, initial=initial)
        return self._render(request, form)

    def post(self, request):
        empresa_id = self._empresa_id(request)
        if not empresa_id:
            messages.error(request, "Selecione a empresa (Medicinarte) antes de replicar.")
            return redirect("empresa:lista")
        form = ReplicarTabelaPrecoForm(request.POST, empresa_id=empresa_id)
        origem, destino, atualizar_existentes, form_errors = self._resolver_cabecalhos_post(
            request, empresa_id, form
        )
        if not origem or not destino:
            detail = ""
            if form_errors:
                detail = f" Detalhe: {form_errors.as_text()}"
            messages.error(
                request,
                "Não foi possível replicar. Escolha origem e destino (IDs numéricos "
                f"do cabeçalho, ex. JARDEL=7, ABDES=6).{detail}",
            )
            return self._render(request, form)

        try:
            resultado = replicar_tabela_preco(
                origem,
                destino,
                atualizar_existentes=atualizar_existentes,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return self._render(request, form)

        if resultado.total_origem == 0:
            messages.warning(
                request,
                f"A origem «{origem.convenio} — {origem.nome_tabela}» não tem preços "
                f"(0 itens). Escolha o cabeçalho que mostra quantidade > 0 na lista.",
            )
            return self._render(request, form)

        if resultado.criados == 0 and resultado.atualizados == 0:
            total_destino = TabelaPreco.objects.filter(cabecalho_id=destino.pk).count()
            if total_destino > 0:
                messages.success(
                    request,
                    f"O destino «{destino.convenio} — {destino.nome_tabela}» (id {destino.pk}) "
                    f"já tem {total_destino} preços ({resultado.pulados} iguais à origem). "
                    f"Abrindo a lista filtrada por este cabeçalho.",
                )
                return redirect(
                    f"{reverse('servicos_medicos:tabela_list')}?cabecalho_id={destino.pk}"
                )
            messages.error(
                request,
                f"Nenhum preço foi gravado no destino «{destino.convenio} — {destino.nome_tabela}» "
                f"(id {destino.pk}). Origem tinha {resultado.total_origem} exames.",
            )
            return self._render(request, form)

        total_destino = TabelaPreco.objects.filter(cabecalho_id=destino.pk).count()
        messages.success(
            request,
            f"Replicação concluída: {resultado.criados} criados, "
            f"{resultado.atualizados} atualizados, {resultado.pulados} mantidos "
            f"→ «{destino.convenio} — {destino.nome_tabela}» (id {destino.pk}, "
            f"total no destino: {total_destino}).",
        )
        return redirect(f"{reverse('servicos_medicos:tabela_list')}?cabecalho_id={destino.pk}")

    def _render(self, request, form):
        empresa_id = self._empresa_id(request)
        from django.shortcuts import render

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "descricao": "Replicar tabela de preços",
            },
        )
