from django import forms
from .models import Convenio, ServicosMedicos, TabelaPreco, Cabecalho

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
    atualizar_existentes = forms.BooleanField(
        required=False,
        initial=True,
        label="Atualizar preços que já existirem no destino",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
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