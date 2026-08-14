from django import forms

from .models import (
    AtendenteAcademia,
    Indicador,
    LancamentoVendasDiario,
    PeriodoAcademia,
    obter_periodo_mm_aaaa,
    obter_periodo_por_data,
)


class IndicadorForm(forms.ModelForm):
    class Meta:
        model = Indicador
        fields = ['area', 'nome', 'ordem', 'ativo', 'premiacao', 'proporcao']
        widgets = {
            'area': forms.Select(attrs={'class': 'form-select'}),
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'premiacao': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.01'}),
            'proporcao': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.01'}),
        }


class DadosPeriodoAcademiaForm(forms.ModelForm):
    class Meta:
        model = PeriodoAcademia
        fields = ['data_referencia', 'qt_ativos', 'qt_cancelados']
        widgets = {
            'data_referencia': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
            'qt_ativos': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1}),
            'qt_cancelados': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1}),
        }


class AtendenteAcademiaForm(forms.ModelForm):
    class Meta:
        model = AtendenteAcademia
        fields = ['nome', 'ordem', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class LancamentoAtendenteDiaForm(forms.ModelForm):
    atendente = forms.ModelChoiceField(
        label='Atendente',
        queryset=AtendenteAcademia.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_atendente'}),
    )
    atend_oport = forms.IntegerField(
        label='Oport.',
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_atend_oport'}),
    )
    atend_balcao = forms.IntegerField(
        label='Vendas (balcão)',
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_atend_balcao'}),
    )
    atend_site = forms.IntegerField(
        label='Site',
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_atend_site'}),
    )
    atend_cancel = forms.IntegerField(
        label='Cancel.',
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_atend_cancel'}),
    )

    class Meta:
        model = LancamentoVendasDiario
        fields = ['data']
        widgets = {
            'data': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
        }

    def __init__(self, *args, empresa_id=None, ano_ref=None, mes_ref=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa_id = empresa_id
        self.ano_ref = ano_ref
        self.mes_ref = mes_ref
        if empresa_id:
            self.fields['atendente'].queryset = (
                AtendenteAcademia.objects.filter(empresa_id=empresa_id, ativo=True).order_by('ordem', 'nome')
            )

    def clean(self):
        cleaned = super().clean()
        data = cleaned.get('data')
        if not data and self.instance and self.instance.pk:
            data = self.instance.data
        if not data:
            return cleaned
        if self.ano_ref and self.mes_ref:
            if data.year != self.ano_ref or data.month != self.mes_ref:
                self.add_error(
                    'data',
                    f'A data deve ser de {self.mes_ref:02d}/{self.ano_ref}.',
                )
        if self.empresa_id:
            periodo = obter_periodo_por_data(self.empresa_id, data)
            if not periodo:
                self.add_error(
                    None,
                    f'Cadastre os dados de {data.month:02d}/{data.year} no Dashboard de Academia.',
                )
            elif not periodo.qt_ativos:
                self.add_error(
                    None,
                    f'Informe a qt. ativos de {data.month:02d}/{data.year} no Dashboard de Academia.',
                )
        return cleaned


class LancamentoCancelamentosDiaForm(forms.ModelForm):
    def __init__(self, *args, empresa_id=None, ano_ref=None, mes_ref=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa_id = empresa_id
        self.ano_ref = ano_ref
        self.mes_ref = mes_ref

    def clean(self):
        cleaned = super().clean()
        data = cleaned.get('data')
        if not data and self.instance and self.instance.pk:
            data = self.instance.data
        if not data:
            return cleaned
        if self.ano_ref and self.mes_ref:
            if data.year != self.ano_ref or data.month != self.mes_ref:
                self.add_error(
                    'data',
                    f'A data deve ser de {self.mes_ref:02d}/{self.ano_ref}.',
                )
        if self.empresa_id:
            periodo = obter_periodo_por_data(self.empresa_id, data)
            if not periodo:
                self.add_error(
                    None,
                    f'Cadastre os dados de {data.month:02d}/{data.year} no Dashboard de Academia.',
                )
            elif not periodo.qt_ativos:
                self.add_error(
                    None,
                    f'Informe a qt. ativos de {data.month:02d}/{data.year} no Dashboard de Academia.',
                )
        return cleaned

    class Meta:
        model = LancamentoVendasDiario
        fields = ['data', 'cancel_inadimplentes', 'cancel_solicitados', 'cancel_negassist']
        labels = {
            'data': 'Dia',
            'cancel_inadimplentes': 'Inad.',
            'cancel_solicitados': 'Solic.',
            'cancel_negassist': 'Neg.',
        }
        widgets = {
            'data': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
            'cancel_inadimplentes': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_cancel_inad'}),
            'cancel_solicitados': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_cancel_solic'}),
            'cancel_negassist': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 1, 'id': 'id_cancel_neg'}),
        }


# Alias para compatibilidade
LancamentoVendasDiarioForm = LancamentoAtendenteDiaForm
