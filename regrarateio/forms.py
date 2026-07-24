from django import forms
from django.forms import ModelForm

from regrarateio.models import LancamentoRateio, RegraRateio, RegraRateioItem


class FormRecalcularRateioGrupo(forms.Form):
    """Troca a regra do título e regenera todas as linhas de rateio proporcionalmente."""

    regra_rateio = forms.ModelChoiceField(
        queryset=RegraRateio.objects.none(),
        label='Regra de rateio',
        help_text='Os valores serão recalculados para todos os sócios conforme os percentuais da regra.',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    confirmo = forms.BooleanField(
        required=True,
        label='Confirmo o recálculo e gravação conforme a prévia acima',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, empresa_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = RegraRateio.objects.all().order_by('nomedaregra')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        self.fields['regra_rateio'].queryset = qs


class FormLancamentoRateio(ModelForm):
    """Edição manual de um lançamento de rateio (origem do título não é alterada)."""

    class Meta:
        model = LancamentoRateio
        fields = ['data_pagamento', 'tipo', 'descricao', 'regra_rateio', 'socio', 'valor']
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'data_pagamento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
                format='%Y-%m-%d',
            ),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'regra_rateio': forms.Select(attrs={'class': 'form-select'}),
            'socio': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        # HTML5 date exige valor em YYYY-MM-DD; sem isso o campo aparece vazio no navegador
        dp = self.fields['data_pagamento']
        dp.input_formats = ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y']
        dp.widget.format = '%Y-%m-%d'
        if empresa:
            self.fields['socio'].queryset = self.fields['socio'].queryset.filter(empresa=empresa)
            self.fields['regra_rateio'].queryset = RegraRateio.objects.filter(empresa=empresa).order_by(
                'nomedaregra'
            )

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        valor = cleaned_data.get('valor')
        if valor is not None and tipo:
            if tipo == LancamentoRateio.TIPO_PGTO and valor > 0:
                cleaned_data['valor'] = -abs(valor)
            elif tipo == LancamentoRateio.TIPO_RECEBIMENTO and valor < 0:
                cleaned_data['valor'] = abs(valor)
        return cleaned_data


class FormRegraItem(ModelForm):
    class Meta:
        model = RegraRateioItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        if empresa:
            self.fields['socios'].queryset = self.fields['socios'].queryset.filter(empresa=empresa)
            self.fields['regrarateio'].queryset = RegraRateio.objects.filter(empresa=empresa).order_by(
                'nomedaregra'
            )


class FormRegraRateio(ModelForm):
    class Meta:
        model = RegraRateio
        fields = ['codigo', 'nomedaregra', 'rateio']
        
    # def clean_rateio(self):
    #     srateio = self.cleaned_data['']
    #     if len(srateio) == 'N':
    #         raise forms.ValidationError("Sobrenome precisa conter mais de 3 caracteres.")
    #     return srateio