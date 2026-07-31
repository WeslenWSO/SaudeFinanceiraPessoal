from django import forms
from django.core.exceptions import ValidationError

from .menu import CODIGOS_MENU, opcoes_permissao_por_secao
from .models import Usuario


class CheckboxPermissoesMenuWidget(forms.Widget):
    template_name = 'widgets/checkbox_permissoes_menu.html'

    def __init__(self, secoes=None, attrs=None):
        super().__init__(attrs)
        self.secoes = secoes or opcoes_permissao_por_secao()

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selecionados = set(value or [])
        context['widget']['secoes'] = self.secoes
        context['widget']['selecionados'] = selecionados
        return context

    def value_from_datadict(self, data, files, name):
        return data.getlist(name)


class CheckboxPermissoesMenuField(forms.MultipleChoiceField):
    widget = CheckboxPermissoesMenuWidget

    def __init__(self, **kwargs):
        choices = [
            (item['codigo'], item['rotulo'])
            for secao in opcoes_permissao_por_secao()
            for item in secao['itens']
        ]
        kwargs.setdefault('choices', choices)
        kwargs.setdefault('required', False)
        kwargs.setdefault(
            'label',
            'Permissões do menu',
        )
        kwargs.setdefault(
            'help_text',
            'Marque as opções que este usuário poderá ver no menu após o login.',
        )
        super().__init__(**kwargs)

    def clean(self, value):
        cleaned = super().clean(value)
        return [c for c in cleaned if c in CODIGOS_MENU]


class UsuarioForm(forms.ModelForm):
    senha = forms.CharField(
        label='Senha de login',
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'autocomplete': 'new-password'},
        ),
        help_text='Obrigatoria ao criar. Deixe em branco na edicao para nao alterar.',
    )
    confirmar_senha = forms.CharField(
        label='Confirmar senha',
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'autocomplete': 'new-password'},
        ),
    )
    permissoes_menu = CheckboxPermissoesMenuField()

    class Meta:
        model = Usuario
        fields = ['empresa', 'usuario', 'lastname', 'email', 'avatar']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True
        if self.instance.pk:
            from .permissoes_menu import permissoes_para_formulario
            self.fields['permissoes_menu'].initial = list(permissoes_para_formulario(self.instance))
        else:
            self.fields['permissoes_menu'].initial = list(CODIGOS_MENU)

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
