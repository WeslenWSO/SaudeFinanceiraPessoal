from django import forms
from django.core.exceptions import ValidationError

from .models import Usuario


class UsuarioForm(forms.ModelForm):
    senha = forms.CharField(
        label='Senha de login',
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'autocomplete': 'new-password'},
        ),
        help_text='Obrigatoria ao criar. Deixe em branco na edicao para manter a senha atual.',
    )
    confirmar_senha = forms.CharField(
        label='Confirmar senha',
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'autocomplete': 'new-password'},
        ),
    )

    class Meta:
        model = Usuario
        fields = ['empresa', 'usuario', 'lastname', 'email', 'avatar', 'senha', 'confirmar_senha']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True

    def clean(self):
        cleaned = super().clean()
        senha = cleaned.get('senha') or ''
        confirmar = cleaned.get('confirmar_senha') or ''
        criando = not self.instance.pk

        if criando and not senha:
            raise ValidationError({'senha': 'Informe a senha para o novo usuario.'})
        if senha and senha != confirmar:
            raise ValidationError({'confirmar_senha': 'As senhas nao conferem.'})
        if senha and len(senha) < 6:
            raise ValidationError({'senha': 'Use pelo menos 6 caracteres.'})
        return cleaned
