from django import forms

from estoque.models import ProdutoEstoque

_W = 'form-control'


class ProdutoEstoqueForm(forms.ModelForm):
    class Meta:
        model = ProdutoEstoque
        fields = [
            'codigo_produto',
            'descricao',
            'marca',
            'quantidade_estoque',
            'valor_ultima_compra',
            'valor_custo_medio',
            'valor_custo_contabil',
        ]
        widgets = {
            'codigo_produto': forms.TextInput(attrs={'class': _W, 'maxlength': 50}),
            'descricao': forms.TextInput(attrs={'class': _W, 'maxlength': 300}),
            'marca': forms.TextInput(attrs={'class': _W, 'maxlength': 120}),
            'quantidade_estoque': forms.NumberInput(attrs={'class': _W, 'step': '0.001'}),
            'valor_ultima_compra': forms.NumberInput(attrs={'class': _W, 'step': '0.0001'}),
            'valor_custo_medio': forms.NumberInput(attrs={'class': _W, 'step': '0.0001'}),
            'valor_custo_contabil': forms.NumberInput(attrs={'class': _W, 'step': '0.0001'}),
        }
