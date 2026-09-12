from decimal import Decimal

from django import forms
from django.forms import ModelForm

from regrarateio.models import LancamentoRateio, RegraRateio, RegraRateioItem


class FormRecalcularRateioGrupo(forms.Form):
    """Troca a regra do título e regenera todas as linhas de rateio proporcionalmente."""

    regra_rateio = forms.ModelChoiceField(
        queryset=RegraRateio.objects.none(),
        label='Regra de rateio',
        required=False,
        empty_label='— Remover rateio (sem regra) —',
        help_text=(
            'Escolha uma regra para recalcular o rateio. '
            'Deixe em branco para remover: exclui os lançamentos de rateio e limpa a regra no título.'
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    valor_manual = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        max_digits=14,
        decimal_places=2,
        label='Valor manual (sócio informado na regra)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    obs_rateio = forms.CharField(
        required=False,
        max_length=255,
        label='Observação do rateio',
        help_text='Texto gravado na coluna Obs. de cada linha de rateio deste título.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '255', 'placeholder': 'Ex.: participação USG, ajuste manual…'}),
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

    def clean(self):
        cleaned = super().clean()
        regra = cleaned.get('regra_rateio')
        if regra:
            from regrarateio.services import _regra_usa_valor_manual

            itens = list(RegraRateioItem.objects.filter(regrarateio=regra))
            if _regra_usa_valor_manual(regra, itens):
                val = cleaned.get('valor_manual')
                if val is None:
                    self.add_error(
                        'valor_manual',
                        'Informe o valor para o sócio manual (regra por valor na aplicação).',
                    )
        return cleaned


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
        fields = ['regrarateio', 'socios', 'tipo_participacao', 'percRateio']
        widgets = {
            'tipo_participacao': forms.Select(attrs={'class': 'form-select'}),
            'percRateio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        if empresa:
            self.fields['socios'].queryset = self.fields['socios'].queryset.filter(empresa=empresa)
            self.fields['regrarateio'].queryset = RegraRateio.objects.filter(empresa=empresa).order_by(
                'nomedaregra'
            )
        regra = None
        if self.instance and self.instance.pk and self.instance.regrarateio_id:
            regra = self.instance.regrarateio
        elif self.data.get('regrarateio'):
            try:
                regra = RegraRateio.objects.filter(pk=int(self.data['regrarateio'])).first()
            except (TypeError, ValueError):
                regra = None
        elif self.initial.get('regrarateio'):
            rid = self.initial['regrarateio']
            regra = RegraRateio.objects.filter(pk=rid).first() if rid else None
        if regra and regra.modo_alocacao == RegraRateio.MODO_VALOR:
            self.fields['percRateio'].required = False
            self.fields['percRateio'].help_text = (
                'Opcional no modo valor. Usado apenas se houver mais de um sócio residual.'
            )

    def clean(self):
        cleaned = super().clean()
        regra = cleaned.get('regrarateio')
        tipo = cleaned.get('tipo_participacao')
        if not regra:
            return cleaned
        if regra.modo_alocacao == RegraRateio.MODO_VALOR and tipo == RegraRateioItem.TIPO_PERCENTUAL:
            self.add_error(
                'tipo_participacao',
                'No modo «Valor na aplicação», use Manual ou Residual.',
            )
        return cleaned


class FormRegraRateio(ModelForm):
    class Meta:
        model = RegraRateio
        fields = ['codigo', 'nomedaregra', 'rateio', 'modo_alocacao']
        widgets = {
            'modo_alocacao': forms.Select(attrs={'class': 'form-select'}),
        }
