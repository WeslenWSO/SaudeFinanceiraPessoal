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


def _rotulo_cabecalho(cabecalho: Cabecalho) -> str:
    return f"{cabecalho.convenio} — {cabecalho.nome_tabela}"


class ReplicarTabelaPrecoForm(forms.Form):
    cabecalho_origem = forms.ModelChoiceField(
        queryset=Cabecalho.objects.none(),
        label="Copiar preços de (tabela origem)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    cabecalho_destino = forms.ModelChoiceField(
        queryset=Cabecalho.objects.none(),
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
        qs = Cabecalho.objects.none()
        if empresa_id:
            qs = (
                Cabecalho.objects.filter(empresa_id=empresa_id)
                .select_related("convenio", "empresa")
                .order_by("convenio__nome", "nome_tabela")
            )
        for name in ("cabecalho_origem", "cabecalho_destino"):
            field = self.fields[name]
            field.queryset = qs
            field.label_from_instance = _rotulo_cabecalho

    def clean(self):
        cleaned = super().clean()
        origem = cleaned.get("cabecalho_origem")
        destino = cleaned.get("cabecalho_destino")
        if origem and destino and origem.pk == destino.pk:
            raise forms.ValidationError("Escolha cabeçalhos diferentes para origem e destino.")
        return cleaned