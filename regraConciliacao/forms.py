from django import forms
from .models import RegraConciliacao
from categoria.models import Categoria
from cobranca.models import Cobranca
from fornecedor.models import Fornecedor
from cliente.models import Cliente
from extrato.models import Banco, ContaBancaria

class RegraConciliacaoForm(forms.ModelForm):
    class Meta:
        model = RegraConciliacao
        fields = ['categoria', 'forma_pagamento', 'fornecedor', 'cliente', 'conta_bancaria_destino', 'descricao', 'tipo_conciliacao', 'tipo_lancamento', 'definicao_historico']

    def __init__(self, *args, **kwargs):
        self.empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)
        # Cobrança não é por empresa: sempre todas
        self.fields['forma_pagamento'].queryset = Cobranca.objects.all()
        if self.empresa_id:
            self.fields['categoria'].queryset = Categoria.objects.filter(empresa_id=self.empresa_id)
            self.fields['fornecedor'].queryset = Fornecedor.objects.filter(empresa_id=self.empresa_id)
            self.fields['cliente'].queryset = Cliente.objects.filter(empresa_id=self.empresa_id)
            self.fields['conta_bancaria_destino'].queryset = ContaBancaria.objects.filter(empresa_id=self.empresa_id)
        else:
            self.fields['categoria'].queryset = Categoria.objects.none()
            self.fields['fornecedor'].queryset = Fornecedor.objects.none()
            self.fields['cliente'].queryset = Cliente.objects.none()
            self.fields['conta_bancaria_destino'].queryset = ContaBancaria.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        tipo_conciliacao = cleaned_data.get('tipo_conciliacao')
        conta_bancaria_destino = cleaned_data.get('conta_bancaria_destino')
        categoria = cleaned_data.get('categoria')
        forma_pagamento = cleaned_data.get('forma_pagamento')

        if tipo_conciliacao == 'transferencia':
            # Conta Bancária Destino é opcional para Transferência
            pass
        else:
            if not categoria:
                raise forms.ValidationError('Categoria é obrigatória quando Tipo de Conciliação não é Transferência.')
            if not forma_pagamento:
                raise forms.ValidationError('Forma de Pagamento é obrigatória quando Tipo de Conciliação não é Transferência.')

        return cleaned_data