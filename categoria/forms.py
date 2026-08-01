from django import forms

from .models import Categoria


class CategoriaForm(forms.ModelForm):
    vinculo_conta_azul = forms.ChoiceField(
        label='Vincular à categoria Conta Azul',
        required=False,
        help_text='Opcional. Escolha a categoria importada da Conta Azul para vincular este registro.',
    )

    class Meta:
        model = Categoria
        fields = [
            'empresa',
            'nome',
            'grupo',
            'classificacao',
            'sintetico',
            'tipo',
            'bloquear_sync_conta_azul',
            'conta_azul_id',
        ]
        widgets = {
            'bloquear_sync_conta_azul': forms.CheckboxInput(
                attrs={'class': 'form-check-input'},
            ),
            'conta_azul_id': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'UUID Conta Azul (preenchido pela sync ou vínculo)',
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True
        empresa_id = None
        if self.instance and self.instance.empresa_id:
            empresa_id = self.instance.empresa_id
        elif self.initial.get('empresa'):
            empresa_id = self.initial.get('empresa')
        elif self.data.get('empresa'):
            empresa_id = self.data.get('empresa')

        choices = [('', '— Nenhum / manual —')]
        if empresa_id:
            qs = (
                Categoria.objects.filter(empresa_id=empresa_id, conta_azul_id__gt='')
                .exclude(pk=self.instance.pk if self.instance and self.instance.pk else None)
                .order_by('nome')
            )
            for cat in qs:
                rotulo = f'{cat.nome} ({cat.get_tipo_display()})'
                choices.append((cat.conta_azul_id, rotulo))
        self.fields['vinculo_conta_azul'].choices = choices
        if self.instance and self.instance.conta_azul_id:
            self.fields['vinculo_conta_azul'].initial = self.instance.conta_azul_id

    def save(self, commit=True):
        obj = super().save(commit=False)
        vinculo = self.cleaned_data.get('vinculo_conta_azul') or ''
        if vinculo:
            obj.conta_azul_id = vinculo
        if commit:
            obj.save()
        return obj
