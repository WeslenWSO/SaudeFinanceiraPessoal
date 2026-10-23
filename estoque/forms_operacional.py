from django import forms

from estoque.models import ProdutoEstoque, RequisicaoEstoque, RequisicaoEstoqueItem
from estoque.setores import SETOR_TRANSFERENCIA_DESTINOS, SetorEstoque


class GerarEstoqueNotaForm(forms.Form):
    marca = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    unidade_master = forms.CharField(
        max_length=20,
        required=False,
        label='Un. master',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'CX'}),
    )
    data_validade = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
    )


class RequisicaoEstoqueForm(forms.ModelForm):
    class Meta:
        model = RequisicaoEstoque
        fields = ['tipo', 'setor_origem', 'setor_destino', 'setor_consumo', 'observacao']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'setor_origem': forms.Select(attrs={'class': 'form-select'}),
            'setor_destino': forms.Select(attrs={'class': 'form-select'}),
            'setor_consumo': forms.Select(attrs={'class': 'form-select'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        destinos = [('', '—')] + list(SETOR_TRANSFERENCIA_DESTINOS)
        self.fields['setor_destino'].choices = destinos
        consumo = [('', '—')] + list(SetorEstoque.choices)
        self.fields['setor_consumo'].choices = consumo


class RequisicaoItemForm(forms.ModelForm):
    class Meta:
        model = RequisicaoEstoqueItem
        fields = ['produto', 'quantidade']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0.001'}),
        }


class RelatorioEstoqueForm(forms.Form):
    produto = forms.CharField(
        required=False,
        label='Medicamento / material',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
    )
    setor = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + list(SetorEstoque.choices),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    data_inicio = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    data_fim = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
