from django import forms

from .models import TarefaAgendada
from .usuarios_empresa import opcoes_responsavel_empresa

_INPUT_DATA = forms.DateInput(
    format='%Y-%m-%d',
    attrs={'type': 'date', 'class': 'form-control'},
)
_INPUT_HORA = forms.TimeInput(
    format='%H:%M',
    attrs={'type': 'time', 'class': 'form-control'},
)


class TarefaAgendadaForm(forms.ModelForm):
    observacao_passagem = forms.CharField(
        required=False,
        label='Observação da passagem',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Opcional — ao alterar o responsável',
        }),
    )
    tarefa_geral = forms.BooleanField(
        required=False,
        label='Tarefa geral (sem empresa)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = TarefaAgendada
        fields = [
            'competencia_mes',
            'competencia_ano',
            'data',
            'previsao_conclusao',
            'hora_inicio',
            'hora_fim',
            'status',
            'responsavel',
            'titulo',
            'descricao',
            'data_conclusao',
        ]
        widgets = {
            'data': _INPUT_DATA,
            'previsao_conclusao': _INPUT_DATA,
            'hora_inicio': _INPUT_HORA,
            'hora_fim': _INPUT_HORA,
            'data_conclusao': _INPUT_DATA,
            'competencia_mes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'competencia_ano': forms.NumberInput(attrs={'class': 'form-control', 'min': 2000, 'max': 2100}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ('data', 'previsao_conclusao', 'data_conclusao'):
            self.fields[nome].input_formats = ['%Y-%m-%d', '%d/%m/%Y']
            self.fields[nome].widget.format = '%Y-%m-%d'
        for nome in ('hora_inicio', 'hora_fim'):
            self.fields[nome].required = False
            self.fields[nome].input_formats = ['%H:%M', '%H:%M:%S']
            self.fields[nome].widget.format = '%H:%M'

        empresa_id = getattr(empresa, 'id', None) if empresa else None
        if not empresa_id and self.instance.pk and self.instance.empresa_id:
            empresa_id = self.instance.empresa_id
        valor_resp = ''
        if self.is_bound:
            valor_resp = (self.data.get('responsavel') or '').strip()
        elif self.instance.pk:
            valor_resp = (self.instance.responsavel or '').strip()
        else:
            valor_resp = (self.initial.get('responsavel') or '').strip()

        self.fields['responsavel'] = forms.ChoiceField(
            choices=opcoes_responsavel_empresa(empresa_id, valor_resp),
            required=False,
            label='Responsável',
            widget=forms.Select(attrs={'class': 'form-select'}),
        )
        if valor_resp:
            self.fields['responsavel'].initial = valor_resp
