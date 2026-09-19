from django import forms
from django.contrib.auth.models import User

from inventario.models import Inventario, InventarioItem


class InventarioForm(forms.ModelForm):
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
        fields = ('descricao',)
        widgets = {
            'descricao': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ex.: Inventário setembro/2026'},
            ),
        }

    def responsaveis_por_rodada(self) -> dict[int, list[User]]:
        return {
            1: list(self.cleaned_data.get('usuarios_contagem_1') or []),
            2: list(self.cleaned_data.get('usuarios_contagem_2') or []),
            3: list(self.cleaned_data.get('usuarios_contagem_3') or []),
        }


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
