from django import forms

from .models import Emprestimo, IndicadorCalculoSicoob


class EmprestimoForm(forms.ModelForm):
    class Meta:
        model = Emprestimo
        fields = [
            'numero_contrato',
            'banco',
            'cliente',
            'cooperativa',
            'modalidade',
            'valor_contrato',
            'data_operacao',
            'data_vencimento',
            'prazo_dias',
            'valor_tributos',
            'valor_tarifas',
            'valor_registros',
            'valor_servicos_terceiros',
            'saldo_devedor_atualizado',
            'data_extrato',
            'taxa_juros_am',
            'taxa_mora_am',
            'taxa_juros_aa',
            'taxa_multa_am',
            'indice_correcao',
            'pct_correcao_am',
            'indice_correcao_atraso',
            'pct_correcao_atraso_am',
            'indicador',
        ]
        widgets = {
            'numero_contrato': forms.TextInput(attrs={
                'class': 'form-control', 'required': True, 'maxlength': '40',
            }),
            'banco': forms.Select(attrs={'class': 'form-select'}),
            'cliente': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '250'}),
            'cooperativa': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '200'}),
            'modalidade': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '200'}),
            'valor_contrato': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'required': True,
            }),
            'data_operacao': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
            'data_vencimento': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
            'prazo_dias': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'step': '1',
            }),
            'valor_tributos': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'valor_tarifas': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'valor_registros': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'valor_servicos_terceiros': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'saldo_devedor_atualizado': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'data_extrato': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
            'taxa_juros_am': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'taxa_mora_am': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'taxa_juros_aa': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'taxa_multa_am': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'indice_correcao': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': '40',
            }),
            'pct_correcao_am': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'indice_correcao_atraso': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': '40',
            }),
            'pct_correcao_atraso_am': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'indicador': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa = empresa

        self.fields['numero_contrato'].required = True
        self.fields['valor_contrato'].required = True
        self.fields['banco'].empty_label = '— Selecione o banco —'
        self.fields['indicador'].queryset = IndicadorCalculoSicoob.objects.filter(
            ativo=True,
        ).order_by('codigo')
        self.fields['indicador'].empty_label = '— Selecione o indicador —'

        for name in ('data_operacao', 'data_vencimento', 'data_extrato'):
            self.fields[name].input_formats = ['%Y-%m-%d', '%d/%m/%Y']

    def clean_numero_contrato(self):
        numero = (self.cleaned_data.get('numero_contrato') or '').strip()
        if not numero:
            raise forms.ValidationError('Informe o número do contrato.')
        if self.empresa and Emprestimo.objects.filter(
            empresa=self.empresa,
            numero_contrato=numero,
        ).exists():
            raise forms.ValidationError(
                f'Já existe o contrato {numero} para esta empresa.',
            )
        return numero

    def save(self, commit=True):
        obj = super().save(commit=False)
        indicador = self.cleaned_data.get('indicador')
        if indicador:
            obj.indicador_calculo = indicador.rotulo or f'{indicador.codigo}-{indicador.nome}'
        if commit:
            obj.save()
        return obj
