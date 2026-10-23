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
        fields = ['tipo', 'setor_origem', 'setor_destino', 'observacao']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_requisicao'}),
            'setor_origem': forms.Select(attrs={'class': 'form-select', 'id': 'id_setor_origem'}),
            'setor_destino': forms.Select(attrs={'class': 'form-select', 'id': 'id_setor_destino'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        destinos = [('', '—')] + list(SETOR_TRANSFERENCIA_DESTINOS)
        self.fields['setor_destino'].choices = destinos
        self.fields['setor_destino'].label = 'Setor destino'

        setores_origem = [('', '—')] + list(SETOR_TRANSFERENCIA_DESTINOS)
        self.fields['setor_origem'].choices = setores_origem
        self.fields['setor_origem'].label = 'Setor (estoque de origem)'

        tipo = None
        if self.data.get('tipo'):
            tipo = self.data.get('tipo')
        elif self.instance.pk:
            tipo = self.instance.tipo

        if tipo == RequisicaoEstoque.Tipo.BAIXA_SETOR:
            self.fields['setor_destino'].required = False
            self.fields['setor_destino'].widget = forms.HiddenInput()
        else:
            self.fields['setor_origem'].required = False
            self.fields['setor_origem'].widget = forms.HiddenInput()
            if not self.initial.get('setor_origem'):
                self.initial['setor_origem'] = SetorEstoque.FARMACIA

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')
        destino = cleaned.get('setor_destino') or ''
        origem = cleaned.get('setor_origem') or ''

        if tipo in (RequisicaoEstoque.Tipo.TRANSFERENCIA, RequisicaoEstoque.Tipo.BAIXA_FARMACIA):
            cleaned['setor_origem'] = SetorEstoque.FARMACIA
            if not destino:
                self.add_error(
                    'setor_destino',
                    'Informe o setor (destino da transferência ou setor de uso na baixa).',
                )
        elif tipo == RequisicaoEstoque.Tipo.BAIXA_SETOR:
            cleaned['setor_destino'] = ''
            if not origem or origem == SetorEstoque.FARMACIA:
                self.add_error('setor_origem', 'Escolha o setor de onde sairá o material.')
        return cleaned


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
