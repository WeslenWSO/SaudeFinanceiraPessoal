from django import forms
from servicos_medicos.replicar_tabela_preco import MODO_COMPLETO, MODO_SOMENTE_FALTANTES

from .models import Convenio, ServicosMedicos, TabelaPreco, Cabecalho

XLSX_MIME = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
)


class PlanilhaExcelImportForm(forms.Form):
    arquivo = forms.FileField(
        label='Planilha Excel (.xlsx)',
        help_text='Use o modelo oficial (primeira linha com os títulos das colunas).',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx'}),
    )
    atualizar_existentes = forms.BooleanField(
        label='Atualizar registros já existentes',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean_arquivo(self):
        f = self.cleaned_data['arquivo']
        name = (f.name or '').lower()
        if not name.endswith('.xlsx'):
            raise forms.ValidationError('Envie um arquivo .xlsx (Excel).')
        if f.size and f.size > 8 * 1024 * 1024:
            raise forms.ValidationError('Arquivo muito grande (máximo 8 MB).')
        return f


class TabelaPrecoImportForm(PlanilhaExcelImportForm):
    cabecalho = forms.ModelChoiceField(
        queryset=Cabecalho.objects.none(),
        required=False,
        label='Cabeçalho (opcional)',
        help_text=(
            'Se escolher um cabeçalho, a planilha só precisa de código do serviço e preços '
            '(convênio e nome da tabela vêm do cabeçalho selecionado).'
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, empresa_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa_id is not None:
            try:
                empresa_id = int(empresa_id)
            except (TypeError, ValueError):
                empresa_id = None
        if empresa_id:
            self.fields['cabecalho'].queryset = (
                Cabecalho.objects.filter(empresa_id=empresa_id)
                .select_related('convenio')
                .order_by('convenio__nome', 'nome_tabela')
            )

class ConvenioForm(forms.ModelForm):
    class Meta:
        model = Convenio
        fields = [
            'empresa',
            'nome',
            'dia_fechamento',
            'dia_abertura',
            'observacao',
            'aliquota_iss_ap',
            'aliquota_pis_ap',
            'aliquota_cofins_ap',
            'aliquota_csll_ap',
            'aliquota_irpj_ap',
        ]
        widgets = {
            'dia_fechamento': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'dia_abertura': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'aliquota_iss_ap': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'aliquota_pis_ap': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'aliquota_cofins_ap': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'aliquota_csll_ap': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'aliquota_irpj_ap': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True
        self.fields['dia_fechamento'].label = 'Dia para fechamento'
        self.fields['dia_abertura'].label = 'Dia para abertura'
        self.fields['observacao'].label = 'Observação (particularidades do convênio)'
        for name in (
            'aliquota_iss_ap',
            'aliquota_pis_ap',
            'aliquota_cofins_ap',
            'aliquota_csll_ap',
            'aliquota_irpj_ap',
        ):
            self.fields[name].label = self.fields[name].label.replace(' apuração', ' (apuração)')

class ServicosMedicosForm(forms.ModelForm):
    class Meta:
        model = ServicosMedicos
        fields = ['codigo', 'servicos', 'porte_anestesico']

    def clean_codigo(self):
        codigo = (self.cleaned_data.get('codigo') or '').strip()
        if not codigo:
            raise forms.ValidationError('Informe o código do serviço.')
        if len(codigo) > 20:
            codigo = codigo[:20]
        qs = ServicosMedicos.objects.filter(codigo=codigo)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                f'Já existe um serviço cadastrado com o código «{codigo}». '
                'Abra a edição desse registro ou use outro código.',
            )
        return codigo


class ServicosMedicosImportForm(PlanilhaExcelImportForm):
    atualizar_existentes = forms.BooleanField(
        label='Atualizar serviços que já existem (mesmo código)',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

class TabelaPrecoForm(forms.ModelForm):
    class Meta:
        model = TabelaPreco
        fields = ['empresa', 'convenio', 'cabecalho', 'codigo_servico', 'preco_apartamento', 'preco_enfermaria']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True
        self.fields['preco_apartamento'].label = 'Preço sem Contraste'
        self.fields['preco_enfermaria'].label = 'Preço com Contraste'
        if self.instance and self.instance.empresa_id:
            self.fields['cabecalho'].queryset = Cabecalho.objects.filter(empresa_id=self.instance.empresa_id)
        elif self.initial.get('empresa'):
            self.fields['cabecalho'].queryset = Cabecalho.objects.filter(empresa_id=self.initial['empresa'])
        else:
            self.fields['cabecalho'].queryset = Cabecalho.objects.none()


def _nome_convenio(cabecalho: Cabecalho) -> str:
    conv = cabecalho.convenio
    if conv is None:
        return "?"
    return getattr(conv, "nome", None) or str(conv)


def _rotulo_cabecalho(cabecalho: Cabecalho, contagens: dict[int, int] | None = None) -> str:
    n = (contagens or {}).get(cabecalho.pk, 0)
    return f"{_nome_convenio(cabecalho)} — {cabecalho.nome_tabela} ({n} preços)"


class ReplicarTabelaPrecoForm(forms.Form):
    """Combo envia o id numérico do cabeçalho (value=7), igual ao manage.py --origem-id."""

    cabecalho_origem = forms.TypedChoiceField(
        coerce=int,
        choices=[],
        label="Copiar preços de (tabela origem)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    cabecalho_destino = forms.TypedChoiceField(
        coerce=int,
        choices=[],
        label="Para (tabela destino)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    modo_replicacao = forms.ChoiceField(
        label="Modo de replicação",
        choices=(
            (
                MODO_SOMENTE_FALTANTES,
                "Somente serviços que faltam no destino (não altera os já cadastrados)",
            ),
            (
                MODO_COMPLETO,
                "Completar faltantes e atualizar preços que já existem no destino",
            ),
        ),
        initial=MODO_SOMENTE_FALTANTES,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, empresa_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa_id is not None:
            try:
                empresa_id = int(empresa_id)
            except (TypeError, ValueError):
                empresa_id = None

        choices_origem: list[tuple[int, str]] = []
        choices_destino: list[tuple[int, str]] = []
        if empresa_id:
            from django.db.models import Q

            from servicos_medicos.replicar_tabela_preco import contagem_linhas_origem

            qs = (
                Cabecalho.objects.filter(
                    Q(empresa_id=empresa_id) | Q(empresa_id__isnull=True)
                )
                .select_related("convenio", "empresa")
                .order_by("convenio__nome", "nome_tabela")
            )
            for cab in qs:
                n_orig = contagem_linhas_origem(cab)
                n_dest = TabelaPreco.objects.filter(cabecalho_id=cab.pk).count()
                choices_origem.append((cab.pk, _rotulo_cabecalho(cab, {cab.pk: n_orig})))
                choices_destino.append((cab.pk, _rotulo_cabecalho(cab, {cab.pk: n_dest})))

        self.fields["cabecalho_origem"].choices = [("", "— Selecione —")] + choices_origem
        self.fields["cabecalho_destino"].choices = [("", "— Selecione —")] + choices_destino
        for name in ("cabecalho_origem", "cabecalho_destino"):
            self.fields[name].widget.attrs.setdefault("class", "form-select")

    def clean(self):
        cleaned = super().clean()
        origem_id = cleaned.get("cabecalho_origem")
        destino_id = cleaned.get("cabecalho_destino")
        if origem_id and destino_id and origem_id == destino_id:
            raise forms.ValidationError("Escolha cabeçalhos diferentes para origem e destino.")
        return cleaned