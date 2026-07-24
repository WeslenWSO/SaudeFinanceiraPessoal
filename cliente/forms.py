from django import forms
from .models import Cliente

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['empresa', 'razao', 'codigo_externo', 'cnpj', 'telefone', 'descricao_extrato_bancario']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make empresa readonly
        self.fields['empresa'].disabled = True
        self.fields['descricao_extrato_bancario'].required = False
        self.fields['descricao_extrato_bancario'].widget.attrs.update(
            {
                'class': 'form-control',
                'placeholder': 'Como o nome aparece no extrato (conciliação automática)',
                'autocomplete': 'off',
            }
        )