from django import forms

from fornecedor.models import Fornecedor

from estoque.models import NaturezaEstoque, ProdutoEstoque
from estoque.setores import SETOR_LOCALIZACAO_IMOBILIZADO

XLSX_MIME = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
)


class ProdutoEstoqueImportForm(forms.Form):
    arquivo = forms.FileField(
        label='Planilha Excel (.xlsx)',
        help_text='Use o modelo oficial ou colunas equivalentes na primeira linha.',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx'}),
    )
    atualizar_existentes = forms.BooleanField(
        label='Atualizar produtos com o mesmo código',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean_arquivo(self):
        f = self.cleaned_data['arquivo']
        name = (f.name or '').lower()
        if not name.endswith('.xlsx'):
            raise forms.ValidationError('Envie um arquivo .xlsx.')
        if f.size and f.size > 15 * 1024 * 1024:
            raise forms.ValidationError('Arquivo muito grande (máx. 15 MB).')
        return f

_W = 'form-control'


class ProdutoEstoqueForm(forms.ModelForm):
    class Meta:
        model = ProdutoEstoque
        fields = [
            'codigo_produto',
            'descricao',
            'marca',
            'fornecedor',
            'setor_localizacao',
            'unidade_master',
            'quantidade_por_master',
            'unidade',
            'quantidade_estoque',
            'quantidade_estoque_contabil',
            'estoque_minimo',
            'dias_entrega_fornecedor',
            'valor_ultima_compra',
            'valor_custo_medio',
            'valor_custo_contabil',
        ]
        widgets = {
            'codigo_produto': forms.TextInput(attrs={'class': _W, 'maxlength': 50}),
            'descricao': forms.TextInput(attrs={'class': _W, 'maxlength': 300}),
            'marca': forms.TextInput(attrs={'class': _W, 'maxlength': 120}),
            'fornecedor': forms.Select(attrs={'class': 'form-select'}),
            'setor_localizacao': forms.Select(attrs={'class': 'form-select'}),
            'unidade_master': forms.TextInput(attrs={'class': _W, 'maxlength': 20, 'placeholder': 'PCT'}),
            'quantidade_por_master': forms.NumberInput(
                attrs={'class': _W, 'step': '0.001', 'min': '0', 'placeholder': '4'},
            ),
            'unidade': forms.TextInput(attrs={'class': _W, 'maxlength': 20, 'placeholder': 'UN'}),
            'quantidade_estoque': forms.NumberInput(attrs={'class': _W, 'step': '0.001'}),
            'quantidade_estoque_contabil': forms.NumberInput(attrs={'class': _W, 'step': '0.001'}),
            'estoque_minimo': forms.NumberInput(attrs={'class': _W, 'step': '0.001', 'min': '0'}),
            'dias_entrega_fornecedor': forms.NumberInput(
                attrs={'class': _W, 'min': '0', 'placeholder': 'Ex.: 7'},
            ),
            'valor_ultima_compra': forms.NumberInput(attrs={'class': _W, 'step': '0.0001'}),
            'valor_custo_medio': forms.NumberInput(attrs={'class': _W, 'step': '0.0001'}),
            'valor_custo_contabil': forms.NumberInput(attrs={'class': _W, 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)
        self.fields['dias_entrega_fornecedor'].help_text = (
            'Quantos dias o fornecedor costuma demorar para entregar (informação de compras).'
        )
        self.fields['quantidade_por_master'].help_text = (
            'Ex.: informe 4 quando 1 PCT (master) contém 4 UN (unidade de consumo).'
        )
        self.fields['fornecedor'].required = False
        self.fields['fornecedor'].empty_label = '—'
        qs = Fornecedor.objects.all().order_by('razao')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        self.fields['fornecedor'].queryset = qs
        self.fields['setor_localizacao'].required = False
        self.fields['setor_localizacao'].choices = [('', '—')] + list(SETOR_LOCALIZACAO_IMOBILIZADO)
        nat = None
        if self.instance.pk:
            nat = self.instance.natureza
        if nat != NaturezaEstoque.IMOBILIZADO:
            self.fields['setor_localizacao'].widget = forms.HiddenInput()
        self.fields['setor_localizacao'].choices = [('', '—')] + list(SETOR_LOCALIZACAO_IMOBILIZADO)
        self.fields['setor_localizacao'].required = False
        if self.instance.pk and self.instance.natureza != NaturezaEstoque.IMOBILIZADO:
            del self.fields['setor_localizacao']
        else:
            self.fields['setor_localizacao'].help_text = 'Setor clínico onde o bem está instalado.'
