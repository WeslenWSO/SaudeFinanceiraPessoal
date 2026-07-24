from datetime import date

from django import forms

from categoria.models import Categoria

from .models import ItemOrcamento


def _label_categoria(cat: Categoria) -> str:
    """Mesmo padrão usado em Contas a Pagar / Fluxo de Caixa."""
    base = f'{cat.classificacao} {cat.nome}'.strip() if cat.classificacao else (cat.nome or '')
    tipo_lbl = {
        'R': 'Receita',
        'D': 'Despesa',
        'I': 'Investimento',
        'L': 'Distr. lucro',
    }.get(cat.tipo or '', '')
    return f'{base} ({tipo_lbl})' if tipo_lbl else base


class ItemOrcamentoForm(forms.ModelForm):
    class Meta:
        model = ItemOrcamento
        fields = [
            'nome',
            'categoria',
            'observacao',
            'forma_calculo',
            'valor_mensal',
            'valor_min',
            'valor_max',
            'aliquota_pct',
            'data_inicio',
            'qtd_meses',
            'ordem',
            'ativo',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'forma_calculo': forms.Select(attrs={'class': 'form-select'}),
            'valor_mensal': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'valor_min': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'valor_max': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
            }),
            'aliquota_pct': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'min': '0',
            }),
            'data_inicio': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': 'form-control', 'type': 'date'},
            ),
            'qtd_meses': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'max': '120', 'step': '1',
            }),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, tipo=None, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipo = tipo or (self.instance.tipo if self.instance and self.instance.pk else None)
        self.empresa = empresa or (
            self.instance.empresa if self.instance and self.instance.pk else None
        )

        self.fields['data_inicio'].input_formats = ['%Y-%m-%d', '%d/%m/%Y']
        self.fields['data_inicio'].required = True
        self.fields['qtd_meses'].required = True
        self.fields['categoria'].required = False
        self.fields['categoria'].empty_label = '— Selecione a categoria —'
        self.fields['categoria'].label_from_instance = _label_categoria

        if not self.instance.pk:
            self.fields['data_inicio'].initial = date.today().replace(day=1)
            self.fields['qtd_meses'].initial = 12

        # Tabela categoria.Categoria da empresa (mesmo cadastro do sistema)
        empresa_id = getattr(self.empresa, 'pk', None) or self.empresa
        if empresa_id:
            qs_cat = (
                Categoria.objects
                .filter(empresa_id=empresa_id)
                .exclude(sintetico='S')
                .order_by('tipo', 'classificacao', 'nome')
            )
            if self.tipo == ItemOrcamento.TIPO_RECEITA:
                qs_cat = qs_cat.filter(tipo='R')
            else:
                # Despesas / impostos: D, I e L (como no fluxo de caixa)
                qs_cat = qs_cat.filter(tipo__in=('D', 'I', 'L'))
        else:
            qs_cat = Categoria.objects.none()
        self.fields['categoria'].queryset = qs_cat

        # Semi-fixas: destaca faixa
        if self.tipo == ItemOrcamento.TIPO_SEMI_FIXA:
            self.fields['valor_mensal'].help_text = 'Valor médio previsto (opcional se informar mín/máx).'
            self.fields['valor_min'].required = False
            self.fields['valor_max'].required = False

        # Impostos e variáveis: alíquota em destaque
        if self.tipo in (ItemOrcamento.TIPO_IMPOSTO, ItemOrcamento.TIPO_VARIAVEL):
            self.fields['forma_calculo'].help_text = (
                'Use % sobre receitas para calcular a partir do total de receitas previstas.'
            )
        else:
            self.fields['forma_calculo'].initial = ItemOrcamento.FORMA_FIXO
            self.fields['valor_min'].widget = forms.HiddenInput()
            self.fields['valor_max'].widget = forms.HiddenInput()

        if self.tipo == ItemOrcamento.TIPO_RECEITA:
            self.fields['forma_calculo'].widget = forms.HiddenInput()
            self.fields['forma_calculo'].initial = ItemOrcamento.FORMA_FIXO
            self.fields['aliquota_pct'].widget = forms.HiddenInput()

        if self.tipo == ItemOrcamento.TIPO_FIXA:
            self.fields['aliquota_pct'].widget = forms.HiddenInput()
            self.fields['forma_calculo'].widget = forms.HiddenInput()
            self.fields['forma_calculo'].initial = ItemOrcamento.FORMA_FIXO

    def clean_qtd_meses(self):
        n = self.cleaned_data.get('qtd_meses') or 1
        if n < 1:
            raise forms.ValidationError('Informe ao menos 1 mês.')
        if n > 120:
            raise forms.ValidationError('Máximo de 120 meses (10 anos).')
        return n
