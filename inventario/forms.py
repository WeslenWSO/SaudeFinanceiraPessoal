from django import forms
from django.contrib.auth.models import User

from estoque.models import NaturezaEstoque, ProdutoEstoque
from estoque.setores import SETOR_LISTA_CEGA_FARMACIA

from inventario.models import Inventario, InventarioItem


class InventarioForm(forms.ModelForm):
    produto_inventario_ids = forms.ModelMultipleChoiceField(
        queryset=ProdutoEstoque.objects.none(),
        required=False,
        label='Produtos do inventário',
        widget=forms.MultipleHiddenInput(),
    )
    usuarios_contagem_1 = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        label='Usuários — 1ª contagem',
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-sm', 'size': 6}),
    )
    usuarios_contagem_2 = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        label='Usuários — 2ª contagem',
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-sm', 'size': 6}),
    )
    usuarios_contagem_3 = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        required=False,
        label='Usuários — 3ª contagem',
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-sm', 'size': 6}),
    )

    class Meta:
        model = Inventario
        fields = ('descricao', 'setor')
        widgets = {
            'descricao': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ex.: Inventário setembro/2026'},
            ),
            'setor': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, empresa_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['setor'].choices = SETOR_LISTA_CEGA_FARMACIA
        self.fields['setor'].help_text = (
            'Informe onde você está contando: depósito central (Farmácia) '
            'ou material já transferido para um setor clínico.'
        )
        if self.instance and self.instance.pk:
            self.fields['setor'].disabled = True
            self.fields.pop('produto_inventario_ids', None)
        elif empresa_id:
            self.fields['produto_inventario_ids'].queryset = ProdutoEstoque.objects.filter(
                empresa_id=empresa_id,
                natureza=NaturezaEstoque.CONSUMIVEL,
            ).order_by('codigo_produto', 'descricao')
            self.fields['produto_inventario_ids'].help_text = (
                'Busque por código ou descrição e adicione na grade. '
                'Se nenhum produto for incluído, entram todos os consumíveis do estoque.'
            )

    def produtos_selecionados_ids(self) -> list[int] | None:
        if 'produto_inventario_ids' not in self.fields:
            return None
        produtos = self.cleaned_data.get('produto_inventario_ids')
        if not produtos:
            return None
        return list(produtos.values_list('pk', flat=True))

    def responsaveis_por_rodada(self) -> dict[int, list[User]]:
        return {
            1: list(self.cleaned_data.get('usuarios_contagem_1') or []),
            2: list(self.cleaned_data.get('usuarios_contagem_2') or []),
            3: list(self.cleaned_data.get('usuarios_contagem_3') or []),
        }


class InventarioAdicionarProdutosForm(forms.Form):
    produtos = forms.ModelMultipleChoiceField(
        queryset=ProdutoEstoque.objects.none(),
        required=True,
        label='Incluir produtos do estoque',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 12}),
    )

    def __init__(self, *args, inventario: Inventario, **kwargs):
        super().__init__(*args, **kwargs)
        ja_inclusos = inventario.itens.values_list('codigo_produto', flat=True)
        self.fields['produtos'].queryset = (
            ProdutoEstoque.objects.filter(empresa_id=inventario.empresa_id)
            .exclude(codigo_produto__in=ja_inclusos)
            .order_by('codigo_produto', 'descricao')
        )


class InventarioItemContagemForm(forms.ModelForm):
    contagem_valor = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=3,
        label='Quantidade contada',
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.001'}),
    )

    class Meta:
        model = InventarioItem
        fields = ()

    def __init__(self, *args, rodada: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        self.rodada = rodada
        valor = self.instance.valor_contagem(rodada)
        if valor is not None and not self.is_bound:
            self.fields['contagem_valor'].initial = valor

    def save(self, commit=True):
        item: InventarioItem = super().save(commit=False)
        valor = self.cleaned_data.get('contagem_valor')
        campo = f'contagem_{self.rodada}'
        setattr(item, campo, valor)
        if commit:
            item.save()
        return item
